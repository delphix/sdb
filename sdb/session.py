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
accesses, objects, symbols) into a portable .sdb bundle file, and replay
those sessions offline without the original crash dump.

The .sdb bundle is a ZIP archive containing:
- metadata.json: Version, timestamp, original dump info
- memory.bin.gz: Gzip-compressed binary memory trace
- objects.json: Object name to address/type mapping
- symbols.json: Address to symbol name mapping
- threads.json: Thread ID to stack PCs for stack trace replay
"""

# pylint: disable=too-many-lines

import gzip
import json
import struct
import zipfile
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import drgn
from drgn import TypeKind

# Bundle file format constants
BUNDLE_VERSION = 1
MEMORY_MAGIC = b'SMEM'  # SDB MEMory
MEMORY_VERSION = 1

# Fat read alignment (256 bytes as per design decision)
FAT_READ_ALIGNMENT = 256
FAT_READ_MASK = ~(FAT_READ_ALIGNMENT - 1)


@dataclass
class MemoryRecord:
    """A single memory read record."""
    address: int
    data: bytes
    seq_id: int = 0


@dataclass
class ObjectRecord:
    """A recorded object with its address and type."""
    name: str
    address: int
    type_name: str


@dataclass
class SymbolRecord:
    """A recorded symbol with its address range."""
    name: str
    address: int
    size: int = 0


@dataclass
class ThreadRecord:
    """A recorded thread's stack trace with optional stack memory."""
    tid: int
    pcs: List[int] = field(default_factory=list)
    stack_start: int = 0  # Stack memory start address
    stack_end: int = 0  # Stack memory end address
    comm: str = ""  # Thread comm name (for display)
    task_addr: int = 0  # task_struct address (for replay pipelines)


class SparseMemory:
    """
    A sparse memory backend that stores disjoint memory segments.

    Uses last-write-wins semantics for overlapping regions during loading.
    Segments are kept sorted by address for efficient binary search lookups.
    """

    def __init__(self) -> None:
        # List of (start_addr, end_addr, data) tuples, sorted by start_addr
        self.segments: List[Tuple[int, int, bytes]] = []

    def write(self, address: int, data: bytes) -> None:
        """
        Write data to the sparse memory, handling overlaps with last-write-wins.
        """
        if not data:
            return

        new_start = address
        new_end = address + len(data)

        # Find and handle overlapping segments
        # Remove segments that are completely covered
        # Trim segments that partially overlap
        new_segments: List[Tuple[int, int, bytes]] = []

        for seg_start, seg_end, seg_data in self.segments:
            if seg_end <= new_start or seg_start >= new_end:
                # No overlap, keep as-is
                new_segments.append((seg_start, seg_end, seg_data))
            else:
                # Overlap exists - trim or split the old segment
                # Keep part before new write
                if seg_start < new_start:
                    keep_len = new_start - seg_start
                    new_segments.append(
                        (seg_start, new_start, seg_data[:keep_len]))

                # Keep part after new write
                if seg_end > new_end:
                    skip_len = new_end - seg_start
                    new_segments.append((new_end, seg_end, seg_data[skip_len:]))

        # Add the new segment
        new_segments.append((new_start, new_end, data))

        # Sort by start address
        new_segments.sort(key=lambda x: x[0])
        self.segments = new_segments

    # pylint: disable=too-many-locals
    def read(self, address: int, size: int) -> bytes:
        """
        Read data from sparse memory.

        Raises FaultError if any requested byte is not in the recorded memory.
        """
        if size == 0:
            return b''

        result = bytearray(size)
        end_address = address + size

        # Find segments that might contain our data
        # Use binary search for efficiency
        starts = [s[0] for s in self.segments]

        # Find the first segment that could contain our start address
        idx = bisect_right(starts, address) - 1
        idx = max(idx, 0)

        bytes_filled = 0
        coverage = [False] * size

        while idx < len(self.segments) and bytes_filled < size:
            seg_start, seg_end, seg_data = self.segments[idx]

            if seg_start >= end_address:
                break

            if seg_end <= address:
                idx += 1
                continue

            # Calculate overlap
            overlap_start = max(address, seg_start)
            overlap_end = min(end_address, seg_end)

            if overlap_start < overlap_end:
                # Copy overlapping data
                result_offset = overlap_start - address
                data_offset = overlap_start - seg_start
                copy_len = overlap_end - overlap_start

                result[result_offset:result_offset +
                       copy_len] = seg_data[data_offset:data_offset + copy_len]

                for i in range(result_offset, result_offset + copy_len):
                    if not coverage[i]:
                        coverage[i] = True
                        bytes_filled += 1

            idx += 1

        # Check if all bytes were found
        if bytes_filled < size:
            missing_ranges = self._find_missing_ranges(coverage, address)
            msg = f"Memory not in trace: {missing_ranges[0] if missing_ranges else hex(address)}"
            raise drgn.FaultError(msg, address)

        return bytes(result)

    def _find_missing_ranges(self, coverage: List[bool],
                             base_addr: int) -> List[str]:
        """Find ranges of missing bytes for error reporting."""
        ranges = []
        start = None
        for i, covered in enumerate(coverage):
            if not covered and start is None:
                start = i
            elif covered and start is not None:
                ranges.append(
                    f"{hex(base_addr + start)}-{hex(base_addr + i - 1)}")
                start = None
        if start is not None:
            ranges.append(
                f"{hex(base_addr + start)}-{hex(base_addr + len(coverage) - 1)}"
            )
        return ranges

    def get_total_size(self) -> int:
        """Return total bytes stored in sparse memory."""
        return sum(len(data) for _, _, data in self.segments)

    def get_segment_count(self) -> int:
        """Return number of disjoint segments."""
        return len(self.segments)


# pylint: disable=too-many-instance-attributes
class TraceManager:
    """
    Manages session recording state and memory tracing.

    This class handles:
    - Installing/uninstalling memory read hooks
    - Buffering memory reads with fat read alignment
    - Recording objects, symbols, and thread stacks
    - Saving and loading .sdb bundle files
    """

    def __init__(self) -> None:
        self.is_recording = False
        self.is_replay = False
        self.output_path: Optional[str] = None
        self.original_read: Optional[Callable[..., bytes]] = None
        self._recording_prog: Optional[drgn.Program] = None

        # Recording buffers
        self.memory = SparseMemory()
        self.objects: Dict[str, ObjectRecord] = {}
        self.symbols: Dict[int, SymbolRecord] = {}
        self.threads: Dict[int, ThreadRecord] = {}

        # Sequence counter for ordering
        self.seq_counter = 0

        # Metadata
        self.metadata: Dict[str, Any] = {}

        # For replay mode
        self.replay_memory: Optional[SparseMemory] = None

    def start_recording(self, prog: drgn.Program, output_path: str) -> None:
        """
        Start recording memory accesses to the specified output file.

        Installs a hook on prog.read() to capture all memory reads.
        """
        if self.is_recording:
            raise RuntimeError("Recording already in progress")

        if self.is_replay:
            raise RuntimeError("Cannot record while in replay mode")

        self.output_path = output_path
        self.is_recording = True
        self.seq_counter = 0

        # Clear buffers
        self.memory = SparseMemory()
        self.objects = {}
        self.symbols = {}
        self.threads = {}

        # Store metadata about the session
        platform = prog.platform
        is_kernel = bool(prog.flags & drgn.ProgramFlags.IS_LINUX_KERNEL)
        self.metadata = {
            'version': BUNDLE_VERSION,
            'timestamp': datetime.now().isoformat(),
            'platform': str(platform) if platform else 'unknown',
            'arch': platform.arch.name if platform else 'unknown',
            'flags': platform.flags.value if platform else 0,
            'session_type': 'kernel' if is_kernel else 'userland',
        }

        # Try to capture kernel info for KASLR handling during replay
        self._capture_kernel_info(prog)

        # Install the memory read hook
        self._install_read_hook(prog)

    def _capture_kernel_info(self, prog: drgn.Program) -> None:
        """
        Capture kernel information for KASLR handling during replay.

        Tries multiple approaches in order of preference:
        1. vmcoreinfo_data - most comprehensive (includes build ID, KASLR offset, etc.)
        2. _text symbol address - for KASLR offset calculation
        3. _stext symbol address - alternative for KASLR offset

        The vmcoreinfo contains:
        - OSRELEASE: kernel version
        - BUILD-ID: for vmlinux verification
        - KERNELOFFSET: KASLR offset (if KASLR enabled)
        - Various struct offsets and sizes
        """
        # Try to capture vmcoreinfo_data first (most comprehensive)
        try:
            vmcoreinfo_ptr = prog['vmcoreinfo_data']
            vmcoreinfo_size = int(prog['vmcoreinfo_size'])
            if 0 < vmcoreinfo_size < 65536:  # Sanity check
                vmcoreinfo_data = vmcoreinfo_ptr.string_().decode(
                    'utf-8', errors='replace')
                self.metadata['vmcoreinfo'] = vmcoreinfo_data

                # Parse out useful fields
                for line in vmcoreinfo_data.split('\n'):
                    if line.startswith('OSRELEASE='):
                        self.metadata['kernel_release'] = line.split('=', 1)[1]
                    elif line.startswith('BUILD-ID='):
                        self.metadata['kernel_build_id'] = line.split('=', 1)[1]
                    elif line.startswith('KERNELOFFSET='):
                        # KASLR offset in hex
                        offset_str = line.split('=', 1)[1]
                        self.metadata['kaslr_offset'] = int(offset_str, 16)
        except (LookupError, ValueError, drgn.FaultError):
            # vmcoreinfo not available (filtered dump, not a kernel, etc.)
            pass

        # Always try to capture _text address as fallback/verification
        try:
            text_sym = prog.symbol('_text')
            self.metadata['kernel_text_address'] = text_sym.address
        except (LookupError, ValueError):
            pass

        # Also try _stext as alternative
        try:
            stext_sym = prog.symbol('_stext')
            self.metadata['kernel_stext_address'] = stext_sym.address
        except (LookupError, ValueError):
            pass

    def stop_recording(self, prog: drgn.Program) -> str:
        """
        Stop recording and save the bundle to disk.

        Returns the path to the saved bundle.
        """
        if not self.is_recording:
            raise RuntimeError("No recording in progress")

        # Uninstall the hook first
        self._uninstall_read_hook(prog)

        self.is_recording = False

        # Save the bundle
        output_path = self.output_path
        if output_path is None:
            raise RuntimeError("No output path set")

        self.save_bundle(output_path)

        return output_path

    def _install_read_hook(self, prog: drgn.Program) -> None:
        """
        Install the memory read hook with fat read support.

        Since drgn.Program.read is read-only (C extension), we use a different
        approach: we store a reference to prog.read and wrap calls to it through
        our helper methods. SDB commands should use trace_read() instead of
        prog.read() directly when recording is active.

        For automatic tracing, we rely on the snapshot command or explicit
        capture calls.
        """
        self.original_read = prog.read
        self._recording_prog = prog

    def _uninstall_read_hook(self, prog: drgn.Program) -> None:
        """Clear the read hook references."""
        # prog argument kept for API consistency and future use
        _ = prog  # Mark as intentionally unused
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
            self._log_read(aligned_start, fat_data)

            # Return only the requested portion
            offset = address - aligned_start
            return fat_data[offset:offset + size]

        except drgn.FaultError:
            # Fat read failed (hit invalid memory), fall back to exact read
            data = self.original_read(address, size, physical)
            self._log_read(address, data)
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
            pass  # Ignore errors during capture

    def _capture_object_impl(self, obj: drgn.Object, depth: int) -> None:
        """Implementation of object capture, separated for complexity."""
        # Handle pointer values - dereference to capture pointed-to memory
        if obj.type_.kind == TypeKind.POINTER:
            self._capture_pointer(obj, depth)
            return

        # For non-pointers, try to get the object's address
        try:
            addr = int(obj.address_of_())
        except (ValueError, TypeError):
            # Object is a value, not a reference - nothing to capture
            return

        # Use drgn.sizeof() which resolves typedefs to get the actual size
        try:
            size = drgn.sizeof(obj.type_)
        except (TypeError, ValueError):
            size = 0
        if size == 0:
            return

        # Read and trace the memory
        self.trace_read(addr, size)

        # Record the object if it has a meaningful type
        type_name = str(obj.type_)
        if type_name and addr:
            self.record_object(f"obj_{hex(addr)}", addr, type_name)

        # For structs, optionally capture pointer members
        if depth > 0 and obj.type_.kind == TypeKind.STRUCT:
            self._capture_struct_pointers(obj, depth)

    def _capture_pointer(self, obj: drgn.Object, depth: int) -> None:
        """Capture memory pointed to by a pointer object."""
        try:
            ptr_value = int(obj)
            if ptr_value == 0:  # Skip null pointers
                return

            # Get the pointed-to type's size
            pointed_type = obj.type_.type
            try:
                type_size = pointed_type.size
                size = min(type_size, 4096) if type_size else 256
            except AttributeError:
                size = 256  # Default for void or incomplete types

            self.trace_read(ptr_value, size)

            # Record this object
            type_name = str(obj.type_)
            self.record_object(f"ptr_{hex(ptr_value)}", ptr_value, type_name)

            # Recursively capture the pointed-to object if depth > 0
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

    def _log_read(self, address: int, data: bytes) -> None:
        """Log a memory read to the trace buffer."""
        self.memory.write(address, data)
        self.seq_counter += 1

    def record_object(self, name: str, address: int, type_name: str) -> None:
        """Record an object's name, address, and type."""
        self.objects[name] = ObjectRecord(name=name,
                                          address=address,
                                          type_name=type_name)

    def record_symbol(self, address: int, name: str, size: int = 0) -> None:
        """Record a symbol at the given address."""
        self.symbols[address] = SymbolRecord(name=name,
                                             address=address,
                                             size=size)

    def record_thread_stack(self,
                            tid: int,
                            pcs: List[int],
                            task_addr: int = 0) -> None:
        """Record a thread's stack trace as a list of program counters."""
        self.threads[tid] = ThreadRecord(tid=tid, pcs=pcs, task_addr=task_addr)

    def _get_task_stack_bounds(self, task: drgn.Object) -> Tuple[int, int]:
        """
        Get stack memory bounds for a task.

        Returns (stack_start, stack_end) tuple.
        """
        # Linux kernel stack is at task->stack with size THREAD_SIZE
        # THREAD_SIZE is typically 16384 (4 pages) on x86_64
        try:
            stack_base = int(task.stack)
            # Default to 16KB, common on x86_64
            thread_size = 16384
            return (stack_base, stack_base + thread_size)
        except (AttributeError, ValueError):
            return (0, 0)

    def _capture_task_stack_memory(self, task: drgn.Object) -> None:
        """Capture the stack memory for a task."""
        stack_start, stack_end = self._get_task_stack_bounds(task)
        if stack_start and stack_end and self.original_read:
            try:
                stack_data = self.original_read(stack_start,
                                                stack_end - stack_start, False)
                self.memory.write(stack_start, stack_data)
            except drgn.FaultError:
                pass  # Stack memory not readable

    def capture_all_stacks(self,
                           prog: drgn.Program,
                           include_locals: bool = True) -> int:
        """
        Capture all kernel thread stacks with symbols and optionally stack memory.

        Args:
            prog: The drgn.Program to capture stacks from.
            include_locals: If True, capture stack memory for local variable access.

        Returns:
            Number of threads captured.
        """
        # Import here to avoid circular imports and allow use outside kernel context
        from drgn.helpers.linux.pid import for_each_task

        captured = 0
        # pylint: disable=no-value-for-parameter
        for task in for_each_task(prog):
            tid = int(task.pid)
            try:
                comm = task.comm.string_().decode(errors='replace')
            except (AttributeError, ValueError):
                comm = ""
            pcs: List[int] = []
            task_addr = 0
            try:
                task_addr = int(task.value_())
            except (AttributeError, ValueError, TypeError):
                task_addr = 0

            if include_locals and task_addr:
                # Capture task_struct memory for replay stack unwinding.
                self.capture_object(task, depth=0)

            try:
                for frame in prog.stack_trace(task):
                    pc = frame.pc
                    if pc == 0:
                        continue
                    pcs.append(pc)
                    # Record symbol for this PC
                    try:
                        sym = frame.symbol()
                        self.record_symbol(sym.address, sym.name, sym.size)
                    except LookupError:
                        pass

                if pcs and include_locals:
                    # Capture stack memory for local variable access
                    self._capture_task_stack_memory(task)

                if pcs:
                    stack_start, stack_end = self._get_task_stack_bounds(task)
                    self.threads[tid] = ThreadRecord(
                        tid=tid,
                        pcs=pcs,
                        stack_start=stack_start,
                        stack_end=stack_end,
                        comm=comm,
                        task_addr=task_addr,
                    )
                    captured += 1

            except (ValueError, LookupError):
                pass  # Running task or unwinding failed

        return captured

    def save_bundle(self, path: str) -> None:
        """Save the recorded session to a .sdb bundle file."""
        # Ensure .sdb extension
        if not path.endswith('.sdb'):
            path = path + '.sdb'

        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Write metadata
            zf.writestr('metadata.json',
                        json.dumps(self.metadata, indent=2).encode('utf-8'))

            # Write objects
            objects_data = {
                name: {
                    'address': rec.address,
                    'type_name': rec.type_name
                } for name, rec in self.objects.items()
            }
            zf.writestr('objects.json',
                        json.dumps(objects_data, indent=2).encode('utf-8'))

            # Write symbols (convert int keys to strings for JSON)
            symbols_data = {
                str(addr): {
                    'name': rec.name,
                    'size': rec.size
                } for addr, rec in self.symbols.items()
            }
            zf.writestr('symbols.json',
                        json.dumps(symbols_data, indent=2).encode('utf-8'))

            # Write threads
            threads_data = {
                str(tid): {
                    'pcs': rec.pcs,
                    'stack_start': rec.stack_start,
                    'stack_end': rec.stack_end,
                    'comm': rec.comm,
                    'task_addr': rec.task_addr,
                } for tid, rec in self.threads.items()
            }
            zf.writestr('threads.json',
                        json.dumps(threads_data, indent=2).encode('utf-8'))

            # Write memory as gzip-compressed binary
            memory_bytes = self._serialize_memory()
            compressed = gzip.compress(memory_bytes)
            zf.writestr('memory.bin.gz', compressed)

    def _serialize_memory(self) -> bytes:
        """Serialize memory segments to binary format."""
        parts = []

        # Header: MAGIC (4 bytes) + VERSION (4 bytes, little-endian)
        parts.append(MEMORY_MAGIC)
        parts.append(struct.pack('<I', MEMORY_VERSION))

        # Records: FLAGS (1 byte) + ADDRESS (8 bytes) + SIZE (4 bytes) + DATA
        for start, _end, data in self.memory.segments:
            flags = 0x01  # READ flag
            size = len(data)
            parts.append(struct.pack('<BQI', flags, start, size))
            parts.append(data)

        return b''.join(parts)

    @classmethod
    def load_bundle(cls, path: str) -> 'TraceManager':  # pylint: disable=too-many-locals
        """Load a recorded session from a .sdb bundle file."""
        manager = cls()
        manager.is_replay = True

        with zipfile.ZipFile(path, 'r') as zf:
            # Load metadata
            manager.metadata = json.loads(
                zf.read('metadata.json').decode('utf-8'))

            # Load objects
            objects_data = json.loads(zf.read('objects.json').decode('utf-8'))
            for name, obj in objects_data.items():
                manager.objects[name] = ObjectRecord(name=name,
                                                     address=obj['address'],
                                                     type_name=obj['type_name'])

            # Load symbols
            symbols_data = json.loads(zf.read('symbols.json').decode('utf-8'))
            for addr_str, sym in symbols_data.items():
                addr = int(addr_str)
                manager.symbols[addr] = SymbolRecord(name=sym['name'],
                                                     address=addr,
                                                     size=sym.get('size', 0))

            # Load threads
            threads_data = json.loads(zf.read('threads.json').decode('utf-8'))
            for tid_str, thread in threads_data.items():
                tid = int(tid_str)
                manager.threads[tid] = ThreadRecord(
                    tid=tid,
                    pcs=thread['pcs'],
                    stack_start=thread.get('stack_start', 0),
                    stack_end=thread.get('stack_end', 0),
                    comm=thread.get('comm', ''),
                    task_addr=thread.get('task_addr', 0),
                )

            # Load memory
            compressed = zf.read('memory.bin.gz')
            memory_bytes = gzip.decompress(compressed)
            manager._deserialize_memory(memory_bytes)

        return manager

    def _deserialize_memory(self, data: bytes) -> None:
        """Deserialize memory from binary format."""
        self.memory = SparseMemory()

        if len(data) < 8:
            raise ValueError("Invalid memory file: too short")

        # Parse header
        magic = data[:4]
        if magic != MEMORY_MAGIC:
            raise ValueError(f"Invalid memory file: bad magic {magic!r}")

        version = struct.unpack('<I', data[4:8])[0]
        if version != MEMORY_VERSION:
            raise ValueError(f"Unsupported memory version: {version}")

        # Parse records
        offset = 8
        while offset < len(data):
            if offset + 13 > len(data):
                break  # Not enough data for header

            _flags, address, size = struct.unpack('<BQI',
                                                  data[offset:offset + 13])
            offset += 13

            if offset + size > len(data):
                raise ValueError("Invalid memory file: truncated record")

            record_data = data[offset:offset + size]
            offset += size

            self.memory.write(address, record_data)

    def setup_replay_program(self, prog: drgn.Program) -> None:
        """
        Set up a drgn.Program for replay mode.

        Registers memory segments and finders from the loaded bundle.
        """
        if not self.is_replay:
            raise RuntimeError("Not in replay mode")

        # Create a memory reader callback
        def memory_reader(address: int, count: int, _offset: int,
                          _physical: bool) -> bytes:
            return self.memory.read(address, count)

        # Register the memory segment for the full address space
        # We use a very large range to cover kernel addresses
        prog.add_memory_segment(0, 0xFFFFFFFFFFFFFFFF, memory_reader)

    def get_status(self) -> Dict[str, Any]:
        """Get current session status."""
        return {
            'is_recording': self.is_recording,
            'is_replay': self.is_replay,
            'output_path': self.output_path,
            'memory_segments': self.memory.get_segment_count(),
            'memory_size': self.memory.get_total_size(),
            'objects_count': len(self.objects),
            'symbols_count': len(self.symbols),
            'threads_count': len(self.threads),
        }

    def symbolize_pc(self, pc: int) -> str:
        """
        Convert a PC to symbol+offset string using recorded symbols.

        Args:
            pc: Program counter to symbolize.

        Returns:
            String like "function_name+0x10" or just hex(pc) if no symbol found.
        """
        # Find symbol containing this PC
        for addr, sym_rec in self.symbols.items():
            if sym_rec.size > 0 and addr <= pc < addr + sym_rec.size:
                offset = pc - addr
                return f"{sym_rec.name}+{hex(offset)}"
            if addr == pc:
                # Exact match, even if size is 0
                return sym_rec.name
        return hex(pc)

    def format_recorded_stack(self, tid: int) -> List[str]:
        """
        Format a recorded thread's stack trace for display.

        Args:
            tid: Thread ID to format stack for.

        Returns:
            List of formatted stack frame strings.
        """
        if tid not in self.threads:
            return []

        lines = []
        thread = self.threads[tid]
        for i, pc in enumerate(thread.pcs):
            sym_str = self.symbolize_pc(pc)
            lines.append(f"#{i:<2} {hex(pc)} {sym_str}")
        return lines

    def get_recorded_threads(self) -> Dict[int, ThreadRecord]:
        """Get all recorded threads."""
        return self.threads


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
    Check if we're in replay mode (loaded from bundle).

    Returns:
        True if the trace manager is in replay mode, False otherwise.
    """
    mgr = get_trace_manager()
    return mgr.is_replay
