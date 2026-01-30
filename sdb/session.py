#
# Copyright 2025 CoreWeave
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Session recording and replay functionality for SDB.

This module provides the ability to record SDB debugging sessions (memory
accesses) into a portable vmcore file using kdumpling, and replay those
sessions offline without the original crash dump.

The recorded vmcore is a standard ELF64 file compatible with drgn, crash,
and other debugging tools. SDB-specific metadata can be embedded as custom
ELF note sections.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from kdumpling import CompressionType, KdumpBuilder, OutputFormat

import drgn
from drgn import TypeKind

# Fat read alignment (256 bytes as per design decision)
FAT_READ_ALIGNMENT = 256
FAT_READ_MASK = ~(FAT_READ_ALIGNMENT - 1)

# SDB custom note types (vendor="SDB")
SDB_NOTE_SESSION = 259

# File extension for recorded vmcores
VMCORE_EXTENSION = '.vmcore.recorded'

# Valid format options
VALID_FORMATS = ('elf', 'kdump')

# Valid compression options (for kdump format)
VALID_COMPRESSIONS = ('none', 'zlib', 'lzo', 'snappy', 'zstd')

# Mapping from string names to kdumpling enums
FORMAT_MAP = {
    'elf': OutputFormat.ELF,
    'kdump': OutputFormat.KDUMP_COMPRESSED,
}

COMPRESSION_MAP = {
    'none': CompressionType.NONE,
    'zlib': CompressionType.ZLIB,
    'lzo': CompressionType.LZO,
    'snappy': CompressionType.SNAPPY,
    'zstd': CompressionType.ZSTD,
}


@dataclass
class MemorySegment:
    """A recorded memory segment."""
    address: int
    data: bytes


class SparseMemory:
    """
    A sparse memory backend that stores disjoint memory segments.

    Uses last-write-wins semantics for overlapping regions.
    Optimized for recording - segments are merged at save time.
    """

    def __init__(self) -> None:
        # Dict of address → data for fast updates
        self._segments: Dict[int, bytes] = {}

    def write(self, address: int, data: bytes) -> None:
        """
        Write data to the sparse memory.

        For simplicity during recording, we just store each write.
        Overlaps are handled by storing at the address - later writes
        at the same address win.
        """
        if not data:
            return
        self._segments[address] = data

    def get_segments(self) -> List[Tuple[int, bytes]]:
        """
        Get all segments as (address, data) tuples.

        Merges adjacent/overlapping segments for efficient storage.
        """
        if not self._segments:
            return []

        # Sort by address
        sorted_items = sorted(self._segments.items())

        # Merge overlapping/adjacent segments
        merged: List[Tuple[int, bytearray]] = []
        for addr, data in sorted_items:
            if not merged:
                merged.append((addr, bytearray(data)))
                continue

            last_addr, last_data = merged[-1]
            last_end = last_addr + len(last_data)

            if addr <= last_end:
                # Overlapping or adjacent - extend or merge
                if addr + len(data) > last_end:
                    # Extends past current end
                    overlap = last_end - addr
                    if overlap >= 0:
                        last_data.extend(data[overlap:])
                # else: completely contained, ignore
            else:
                # Gap - start new segment
                merged.append((addr, bytearray(data)))

        return [(addr, bytes(data)) for addr, data in merged]

    def get_total_size(self) -> int:
        """Return total bytes stored in sparse memory."""
        return sum(len(data) for data in self._segments.values())

    def get_segment_count(self) -> int:
        """Return number of segments (before merging)."""
        return len(self._segments)


class TraceManager:  # pylint: disable=too-many-instance-attributes
    """
    Manages session recording state and memory tracing.

    This class handles:
    - Installing/uninstalling memory read hooks
    - Buffering memory reads with fat read alignment
    - Saving vmcore files using kdumpling
    """

    def __init__(self) -> None:
        self.is_recording = False
        self.is_replay = False
        self.output_path: Optional[str] = None
        self.original_read: Optional[Callable[..., bytes]] = None
        self._recording_prog: Optional[drgn.Program] = None

        # Recording buffers
        self.memory = SparseMemory()

        # Metadata
        self.metadata: Dict[str, Any] = {}

        # Output format settings (can be set before stop_recording)
        self.output_format: str = 'elf'  # 'elf' or 'kdump'
        self.compression: str = 'zlib'  # For kdump: 'none', 'zlib', 'lzo', 'snappy', 'zstd'
        self.compression_level: int = 6  # 1-9, only used for kdump format

    def start_recording(self, prog: drgn.Program, output_path: str) -> None:
        """
        Start recording memory accesses to the specified output file.

        Installs a hook on prog.read() to capture all memory reads.
        """
        if self.is_recording:
            raise RuntimeError("Recording already in progress")

        if self.is_replay:
            raise RuntimeError("Cannot record while in replay mode")

        # Ensure correct extension
        if not output_path.endswith(VMCORE_EXTENSION):
            output_path = output_path + VMCORE_EXTENSION

        self.output_path = output_path
        self.is_recording = True

        # Clear buffers
        self.memory = SparseMemory()

        # Store metadata about the session
        platform = prog.platform
        self.metadata = {
            'timestamp': datetime.now().isoformat(),
            'platform': str(platform) if platform else 'unknown',
            'arch': platform.arch.name if platform else 'X86_64',
            'flags': platform.flags.value if platform else 0,
        }

        # Try to capture kernel info for vmcoreinfo
        self._capture_kernel_info(prog)

        # Install the memory read hook
        self._install_read_hook(prog)

    def _capture_kernel_info(self, prog: drgn.Program) -> None:
        """
        Capture kernel information including vmcoreinfo.

        The vmcoreinfo is essential for drgn to properly load the vmcore
        and handle KASLR relocation.
        """
        # Try to capture vmcoreinfo_data (most important)
        try:
            vmcoreinfo_ptr = prog['vmcoreinfo_data']
            vmcoreinfo_size = int(prog['vmcoreinfo_size'])
            if 0 < vmcoreinfo_size < 65536:  # Sanity check
                vmcoreinfo_data = vmcoreinfo_ptr.string_().decode(
                    'utf-8', errors='replace')
                self.metadata['vmcoreinfo'] = vmcoreinfo_data

                # Parse out useful fields for metadata
                for line in vmcoreinfo_data.split('\n'):
                    if line.startswith('OSRELEASE='):
                        self.metadata['kernel_release'] = line.split('=', 1)[1]
        except (LookupError, ValueError, drgn.FaultError):
            pass

    def stop_recording(self, prog: drgn.Program) -> str:
        """
        Stop recording and save the vmcore to disk.

        Returns the path to the saved vmcore file.
        """
        if not self.is_recording:
            raise RuntimeError("No recording in progress")

        # Uninstall the hook first
        self._uninstall_read_hook(prog)

        self.is_recording = False

        # Save the vmcore
        output_path = self.output_path
        if output_path is None:
            raise RuntimeError("No output path set")

        self._save_vmcore(output_path, prog)

        return output_path

    def _save_vmcore(self, path: str, _prog: drgn.Program) -> None:
        """Save the recorded session as a kdumpling vmcore."""
        # Get architecture from program
        arch = self.metadata.get('arch', 'x86_64')
        # Normalize architecture name for kdumpling
        arch_map = {
            'X86_64': 'x86_64',
            'AARCH64': 'aarch64',
            'ARM64': 'aarch64',
            'S390X': 's390x',
            'PPC64': 'ppc64',
            'RISCV64': 'riscv64',
        }
        arch = arch_map.get(arch.upper(), arch.lower())

        builder = KdumpBuilder(arch=arch)

        # Set vmcoreinfo if available
        vmcoreinfo = self.metadata.get('vmcoreinfo')
        if vmcoreinfo:
            builder.set_vmcoreinfo(vmcoreinfo)

        # Add memory segments
        for vaddr, data in self.memory.get_segments():
            builder.add_memory_segment(phys_addr=vaddr,
                                       data=data,
                                       virt_addr=vaddr)

        # Add SDB session metadata as custom note
        session_metadata = {
            'timestamp': self.metadata.get('timestamp'),
            'platform': self.metadata.get('platform'),
            'kernel_release': self.metadata.get('kernel_release'),
        }
        builder.add_custom_note("SDB", SDB_NOTE_SESSION,
                                json.dumps(session_metadata).encode())

        # Write the vmcore with configured format and compression
        output_fmt = FORMAT_MAP.get(self.output_format, OutputFormat.ELF)
        compression = COMPRESSION_MAP.get(self.compression,
                                          CompressionType.ZLIB)

        builder.write(path,
                      format=output_fmt,
                      compression=compression,
                      compression_level=self.compression_level)

    def _install_read_hook(self, prog: drgn.Program) -> None:
        """
        Install the memory read hook reference.

        We store a reference to prog.read for use in trace_read().
        """
        self.original_read = prog.read
        self._recording_prog = prog

    def _uninstall_read_hook(self, prog: drgn.Program) -> None:
        """Clear the read hook references."""
        _ = prog  # Unused, kept for API consistency
        self.original_read = None
        self._recording_prog = None

    def trace_read(self,
                   address: int,
                   size: int,
                   physical: bool = False) -> bytes:
        """
        Read memory and trace it. Use this instead of prog.read() when recording.

        Performs a fat read (256-byte aligned) to capture surrounding memory.
        """
        if self.original_read is None:
            raise RuntimeError("No recording in progress")

        # Calculate fat read boundaries (256-byte aligned)
        aligned_start = address & FAT_READ_MASK
        aligned_end = (address + size + FAT_READ_ALIGNMENT - 1) & FAT_READ_MASK

        try:
            # Try fat read first
            fat_data = self.original_read(aligned_start,
                                          aligned_end - aligned_start, physical)
            self.memory.write(aligned_start, fat_data)

            # Return only the requested portion
            offset = address - aligned_start
            return fat_data[offset:offset + size]

        except drgn.FaultError:
            # Fat read failed, fall back to exact read
            data = self.original_read(address, size, physical)
            self.memory.write(address, data)
            return data

    def capture_object(self, obj: drgn.Object, depth: int = 1) -> None:
        """
        Capture an object's memory into the trace.

        This forces a read of the object's memory and optionally follows
        pointers up to the specified depth.
        """
        if not self.is_recording or self.original_read is None:
            return

        try:
            self._capture_object_impl(obj, depth)
        except (drgn.FaultError, ValueError, TypeError, OverflowError):
            pass

    def _capture_object_impl(self, obj: drgn.Object, depth: int) -> None:
        """Implementation of object capture."""
        if obj.type_.kind == TypeKind.POINTER:
            self._capture_pointer(obj, depth)
            return

        try:
            addr = int(obj.address_of_())
        except (ValueError, TypeError):
            return

        try:
            size = drgn.sizeof(obj.type_)
        except (TypeError, ValueError):
            size = 0
        if size == 0:
            return

        self.trace_read(addr, size)

        if depth > 0 and obj.type_.kind == TypeKind.STRUCT:
            self._capture_struct_pointers(obj, depth)

    def _capture_pointer(self, obj: drgn.Object, depth: int) -> None:
        """Capture memory pointed to by a pointer object."""
        try:
            ptr_value = int(obj)
            if ptr_value == 0:
                return

            pointed_type = obj.type_.type
            try:
                type_size = pointed_type.size
                size = min(type_size, 4096) if type_size else 256
            except AttributeError:
                size = 256

            self.trace_read(ptr_value, size)

            if depth > 0:
                try:
                    pointed = obj[0]
                    self.capture_object(pointed, depth - 1)
                except drgn.FaultError:
                    pass
        except (ValueError, OverflowError):
            pass

    def _capture_struct_pointers(self, obj: drgn.Object, depth: int) -> None:
        """Capture pointer members of a struct."""
        for member in obj.type_.members:
            if member.name:
                try:
                    member_obj = obj.member_(member.name)
                    if member_obj.type_.kind == TypeKind.POINTER:
                        self.capture_object(member_obj, depth - 1)
                except (drgn.FaultError, ValueError, TypeError):
                    pass

    def set_output_format(self, fmt: str) -> None:
        """
        Set the output format for the recorded vmcore.

        Args:
            fmt: 'elf' for standard ELF vmcore, 'kdump' for kdump compressed format
        """
        fmt = fmt.lower()
        if fmt not in VALID_FORMATS:
            raise ValueError(
                f"Invalid format: {fmt}. Valid formats: {VALID_FORMATS}")
        self.output_format = fmt

    def set_compression(self, compression: str, level: int = 6) -> None:
        """
        Set compression for kdump format.

        Args:
            compression: 'none', 'zlib', 'lzo', 'snappy', or 'zstd'
            level: Compression level 1-9 (default 6)

        Note: Compression is only used when output_format is 'kdump'.
              ELF format does not support compression.
        """
        compression = compression.lower()
        if compression not in VALID_COMPRESSIONS:
            raise ValueError(f"Invalid compression: {compression}. "
                             f"Valid options: {VALID_COMPRESSIONS}")
        if not 1 <= level <= 9:
            raise ValueError(f"Compression level must be 1-9, got {level}")
        self.compression = compression
        self.compression_level = level

    def get_status(self) -> Dict[str, Any]:
        """Get current session status."""
        return {
            'is_recording':
                self.is_recording,
            'is_replay':
                self.is_replay,
            'output_path':
                self.output_path,
            'memory_segments':
                self.memory.get_segment_count(),
            'memory_size':
                self.memory.get_total_size(),
            'output_format':
                self.output_format,
            'compression':
                self.compression if self.output_format == 'kdump' else 'n/a',
            'compression_level':
                self.compression_level
                if self.output_format == 'kdump' else 'n/a',
        }


def extract_sdb_notes(vmcore_path: str) -> Optional[Dict[str, Any]]:
    """
    Extract SDB custom notes from a vmcore file.

    Args:
        vmcore_path: Path to the vmcore file.

    Returns:
        Dictionary with SDB metadata, or None if no SDB notes found.
    """
    try:
        from elftools.elf.elffile import ELFFile

        with open(vmcore_path, 'rb') as f:
            elf = ELFFile(f)  # type: ignore[no-untyped-call]
            for segment in elf.iter_segments():  # type: ignore[no-untyped-call]
                if segment['p_type'] == 'PT_NOTE':
                    for note in segment.iter_notes():
                        if note['n_name'] == 'SDB' and note[
                                'n_type'] == SDB_NOTE_SESSION:
                            data = note['n_desc']
                            if isinstance(data, bytes):
                                result: Dict[str, Any] = json.loads(
                                    data.decode('utf-8'))
                                return result
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None


# Global trace manager instance
_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    """Get or create the global trace manager."""
    global _trace_manager  # pylint: disable=global-statement
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager


def reset_trace_manager() -> None:
    """Reset the global trace manager (for testing)."""
    global _trace_manager  # pylint: disable=global-statement
    _trace_manager = None


def is_replay_mode() -> bool:
    """
    Check if we're in replay mode.

    With kdumpling integration, replay mode is simply when we've loaded
    a vmcore via set_core_dump(). This function checks if the trace
    manager has been marked as replay mode.
    """
    mgr = get_trace_manager()
    return mgr.is_replay
