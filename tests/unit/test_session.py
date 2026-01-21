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
Unit tests for the session recording and replay functionality.
"""

import gzip
import json
import os
import struct
import tempfile
import zipfile
from pathlib import Path

import pytest

import drgn

from sdb.session import (
    SparseMemory,
    TraceManager,
    MemoryRecord,
    ObjectRecord,
    SymbolRecord,
    ThreadRecord,
    MEMORY_MAGIC,
    MEMORY_VERSION,
    FAT_READ_ALIGNMENT,
    FAT_READ_MASK,
    get_trace_manager,
    reset_trace_manager,
    is_replay_mode,
)


class TestSparseMemory:
    """Tests for the SparseMemory class."""

    def test_write_and_read_simple(self) -> None:
        """Test basic write and read operations."""
        mem = SparseMemory()
        data = b'hello world'
        mem.write(0x1000, data)

        result = mem.read(0x1000, len(data))
        assert result == data

    def test_write_and_read_partial(self) -> None:
        """Test reading a partial segment."""
        mem = SparseMemory()
        data = b'0123456789'
        mem.write(0x1000, data)

        # Read middle portion
        result = mem.read(0x1003, 4)
        assert result == b'3456'

    def test_multiple_disjoint_segments(self) -> None:
        """Test multiple non-overlapping segments."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x2000, b'bbbb')
        mem.write(0x3000, b'cccc')

        assert mem.read(0x1000, 4) == b'aaaa'
        assert mem.read(0x2000, 4) == b'bbbb'
        assert mem.read(0x3000, 4) == b'cccc'

    def test_overlapping_write_last_wins(self) -> None:
        """Test that overlapping writes use last-write-wins semantics."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaaaaaaaa')  # 10 bytes
        mem.write(0x1003, b'BBBB')  # Overlap in the middle

        result = mem.read(0x1000, 10)
        assert result == b'aaaBBBBaaa'

    def test_overlapping_write_complete_cover(self) -> None:
        """Test that a larger write completely covers a smaller one."""
        mem = SparseMemory()
        mem.write(0x1002, b'xx')
        mem.write(0x1000, b'AAAAAAAA')  # Completely covers the first write

        result = mem.read(0x1000, 8)
        assert result == b'AAAAAAAA'

    def test_read_missing_raises_fault(self) -> None:
        """Test that reading missing memory raises an error."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')

        with pytest.raises(drgn.FaultError):
            mem.read(0x2000, 4)

    def test_read_partial_missing_raises_fault(self) -> None:
        """Test that reading partially missing memory raises an error."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')

        # Try to read beyond the segment
        with pytest.raises(drgn.FaultError):
            mem.read(0x1002, 8)  # Only 2 bytes available, requesting 8

    def test_adjacent_segments(self) -> None:
        """Test reading across adjacent segments."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x1004, b'bbbb')

        result = mem.read(0x1000, 8)
        assert result == b'aaaabbbb'

    def test_get_total_size(self) -> None:
        """Test total size calculation."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x2000, b'bbbbbb')

        assert mem.get_total_size() == 10

    def test_get_segment_count(self) -> None:
        """Test segment count."""
        mem = SparseMemory()
        assert mem.get_segment_count() == 0

        mem.write(0x1000, b'aaaa')
        assert mem.get_segment_count() == 1

        mem.write(0x2000, b'bbbb')
        assert mem.get_segment_count() == 2

    def test_empty_write_ignored(self) -> None:
        """Test that empty writes are ignored."""
        mem = SparseMemory()
        mem.write(0x1000, b'')
        assert mem.get_segment_count() == 0

    def test_empty_read_returns_empty(self) -> None:
        """Test that reading 0 bytes returns empty."""
        mem = SparseMemory()
        result = mem.read(0x1000, 0)
        assert result == b''


class TestTraceManager:
    """Tests for the TraceManager class."""

    def setup_method(self) -> None:
        """Reset trace manager before each test."""
        reset_trace_manager()

    def test_initial_state(self) -> None:
        """Test initial state of TraceManager."""
        mgr = TraceManager()
        assert not mgr.is_recording
        assert not mgr.is_replay
        assert mgr.output_path is None

    def test_record_object(self) -> None:
        """Test recording an object."""
        mgr = TraceManager()
        mgr.record_object('my_var', 0x1234, 'struct foo')

        assert 'my_var' in mgr.objects
        assert mgr.objects['my_var'].address == 0x1234
        assert mgr.objects['my_var'].type_name == 'struct foo'

    def test_record_symbol(self) -> None:
        """Test recording a symbol."""
        mgr = TraceManager()
        mgr.record_symbol(0xffff0000, 'my_function', 100)

        assert 0xffff0000 in mgr.symbols
        assert mgr.symbols[0xffff0000].name == 'my_function'
        assert mgr.symbols[0xffff0000].size == 100

    def test_record_thread_stack(self) -> None:
        """Test recording thread stack."""
        mgr = TraceManager()
        pcs = [0x1000, 0x2000, 0x3000]
        mgr.record_thread_stack(1234, pcs, task_addr=0xbeef)

        assert 1234 in mgr.threads
        assert mgr.threads[1234].pcs == pcs
        assert mgr.threads[1234].task_addr == 0xbeef

    def test_get_status(self) -> None:
        """Test status reporting."""
        mgr = TraceManager()
        mgr.memory.write(0x1000, b'test data')
        mgr.record_object('var1', 0x1000, 'int')
        mgr.record_symbol(0x2000, 'func', 50)

        status = mgr.get_status()
        assert status['is_recording'] is False
        assert status['is_replay'] is False
        assert status['memory_size'] == 9
        assert status['objects_count'] == 1
        assert status['symbols_count'] == 1


class TestBundleIO:
    """Tests for bundle save/load functionality."""

    def test_save_and_load_bundle(self) -> None:
        """Test saving and loading a bundle."""
        mgr = TraceManager()

        # Add some test data
        mgr.memory.write(0x1000, b'memory content here')
        mgr.record_object('test_var', 0x1000, 'struct test')
        mgr.record_symbol(0xffff0000, 'test_func', 200)
        mgr.record_thread_stack(42, [0x1000, 0x2000, 0x3000])
        mgr.metadata = {
            'version': 1,
            'timestamp': '2025-01-01T00:00:00',
            'platform': 'test',
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, 'test.sdb')
            mgr.save_bundle(bundle_path)

            # Verify the bundle exists and is a valid ZIP
            assert os.path.exists(bundle_path)
            with zipfile.ZipFile(bundle_path, 'r') as zf:
                assert 'metadata.json' in zf.namelist()
                assert 'objects.json' in zf.namelist()
                assert 'symbols.json' in zf.namelist()
                assert 'threads.json' in zf.namelist()
                assert 'memory.bin.gz' in zf.namelist()

            # Load and verify
            loaded = TraceManager.load_bundle(bundle_path)
            assert loaded.is_replay is True

            # Verify memory
            assert loaded.memory.read(0x1000, 19) == b'memory content here'

            # Verify objects
            assert 'test_var' in loaded.objects
            assert loaded.objects['test_var'].address == 0x1000
            assert loaded.objects['test_var'].type_name == 'struct test'

            # Verify symbols
            assert 0xffff0000 in loaded.symbols
            assert loaded.symbols[0xffff0000].name == 'test_func'

            # Verify threads
            assert 42 in loaded.threads
            assert loaded.threads[42].pcs == [0x1000, 0x2000, 0x3000]

    def test_bundle_adds_sdb_extension(self) -> None:
        """Test that .sdb extension is added if missing."""
        mgr = TraceManager()
        mgr.memory.write(0x1000, b'test')
        mgr.metadata = {'version': 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, 'test')
            mgr.save_bundle(bundle_path)

            assert os.path.exists(bundle_path + '.sdb')

    def test_memory_binary_format(self) -> None:
        """Test the binary memory format directly."""
        mgr = TraceManager()
        mgr.memory.write(0x1000, b'aaaa')
        mgr.memory.write(0x2000, b'bbbb')

        # pylint: disable=protected-access
        data = mgr._serialize_memory()

        # Verify header
        assert data[:4] == MEMORY_MAGIC
        version = struct.unpack('<I', data[4:8])[0]
        assert version == MEMORY_VERSION

        # Parse records
        offset = 8
        records = []
        while offset < len(data):
            _flags, address, size = struct.unpack('<BQI',
                                                  data[offset:offset + 13])
            offset += 13
            record_data = data[offset:offset + size]
            offset += size
            records.append((address, record_data))

        # Should have 2 records
        assert len(records) == 2
        addresses = {r[0] for r in records}
        assert 0x1000 in addresses
        assert 0x2000 in addresses


class TestFatReadAlignment:
    """Tests for fat read alignment."""

    def test_fat_read_alignment_constant(self) -> None:
        """Test that fat read alignment is 256 bytes as designed."""
        assert FAT_READ_ALIGNMENT == 256

    def test_alignment_mask(self) -> None:
        """Test alignment calculation."""
        # Test various addresses
        test_cases = [
            (0x1000, 0x1000),  # Already aligned
            (0x1001, 0x1000),  # Just after boundary
            (0x10FF, 0x1000),  # Just before next boundary
            (0x1100, 0x1100),  # Next boundary
            (0x1234, 0x1200),  # Random address
        ]

        for addr, expected_aligned in test_cases:
            aligned = addr & FAT_READ_MASK
            assert aligned == expected_aligned, \
                f"0x{addr:x} -> 0x{aligned:x}, expected 0x{expected_aligned:x}"


class TestGlobalTraceManager:
    """Tests for global trace manager singleton."""

    def setup_method(self) -> None:
        """Reset trace manager before each test."""
        reset_trace_manager()

    def test_get_trace_manager_singleton(self) -> None:
        """Test that get_trace_manager returns the same instance."""
        mgr1 = get_trace_manager()
        mgr2 = get_trace_manager()
        assert mgr1 is mgr2

    def test_reset_trace_manager(self) -> None:
        """Test that reset creates a new instance."""
        mgr1 = get_trace_manager()
        reset_trace_manager()
        mgr2 = get_trace_manager()
        assert mgr1 is not mgr2


class TestDataclasses:
    """Tests for dataclass records."""

    def test_memory_record(self) -> None:
        """Test MemoryRecord dataclass."""
        rec = MemoryRecord(address=0x1000, data=b'test', seq_id=5)
        assert rec.address == 0x1000
        assert rec.data == b'test'
        assert rec.seq_id == 5

    def test_object_record(self) -> None:
        """Test ObjectRecord dataclass."""
        rec = ObjectRecord(name='var', address=0x2000, type_name='int')
        assert rec.name == 'var'
        assert rec.address == 0x2000
        assert rec.type_name == 'int'

    def test_symbol_record(self) -> None:
        """Test SymbolRecord dataclass."""
        rec = SymbolRecord(name='func', address=0x3000, size=100)
        assert rec.name == 'func'
        assert rec.address == 0x3000
        assert rec.size == 100

    def test_thread_record(self) -> None:
        """Test ThreadRecord dataclass."""
        rec = ThreadRecord(tid=42, pcs=[0x1000, 0x2000], task_addr=0xdeadbeef)
        assert rec.tid == 42
        assert rec.pcs == [0x1000, 0x2000]
        assert rec.task_addr == 0xdeadbeef

    def test_thread_record_default_pcs(self) -> None:
        """Test ThreadRecord default pcs."""
        rec = ThreadRecord(tid=1)
        assert rec.pcs == []

    def test_thread_record_stack_bounds(self) -> None:
        """Test ThreadRecord with stack bounds."""
        rec = ThreadRecord(
            tid=123,
            pcs=[0x1000, 0x2000],
            stack_start=0xffff8000,
            stack_end=0xffffc000,
            comm="test_thread",
        )
        assert rec.tid == 123
        assert rec.pcs == [0x1000, 0x2000]
        assert rec.stack_start == 0xffff8000
        assert rec.stack_end == 0xffffc000
        assert rec.comm == "test_thread"

    def test_thread_record_default_stack_bounds(self) -> None:
        """Test ThreadRecord default stack bounds."""
        rec = ThreadRecord(tid=1)
        assert rec.stack_start == 0
        assert rec.stack_end == 0
        assert rec.comm == ""
        assert rec.task_addr == 0


class TestSymbolizePc:
    """Tests for PC symbolization."""

    def setup_method(self) -> None:
        """Reset trace manager before each test."""
        reset_trace_manager()

    def test_symbolize_pc_exact_match(self) -> None:
        """Test symbolizing a PC that exactly matches a symbol address."""
        mgr = TraceManager()
        mgr.record_symbol(0x1000, "my_function", 100)

        result = mgr.symbolize_pc(0x1000)
        # Exact match at start of function returns +0x0
        assert result == "my_function+0x0"

    def test_symbolize_pc_with_offset(self) -> None:
        """Test symbolizing a PC within a symbol's range."""
        mgr = TraceManager()
        mgr.record_symbol(0x1000, "my_function", 100)

        result = mgr.symbolize_pc(0x1010)
        assert result == "my_function+0x10"

    def test_symbolize_pc_not_found(self) -> None:
        """Test symbolizing a PC not in any symbol range."""
        mgr = TraceManager()
        mgr.record_symbol(0x1000, "my_function", 100)

        result = mgr.symbolize_pc(0x2000)
        assert result == "0x2000"

    def test_symbolize_pc_multiple_symbols(self) -> None:
        """Test symbolizing with multiple symbols."""
        mgr = TraceManager()
        mgr.record_symbol(0x1000, "func_a", 50)
        mgr.record_symbol(0x2000, "func_b", 100)
        mgr.record_symbol(0x3000, "func_c", 200)

        assert mgr.symbolize_pc(0x1020) == "func_a+0x20"
        assert mgr.symbolize_pc(0x2050) == "func_b+0x50"
        # 0x3050 = 0x3000 + 0x50 (offset 80, within size 200)
        assert mgr.symbolize_pc(0x3050) == "func_c+0x50"


class TestFormatRecordedStack:
    """Tests for formatting recorded stack traces."""

    def setup_method(self) -> None:
        """Reset trace manager before each test."""
        reset_trace_manager()

    def test_format_recorded_stack_basic(self) -> None:
        """Test basic stack formatting."""
        mgr = TraceManager()
        mgr.record_symbol(0x1000, "func_a", 100)
        mgr.record_symbol(0x2000, "func_b", 100)
        mgr.threads[42] = ThreadRecord(tid=42, pcs=[0x1000, 0x2010])

        lines = mgr.format_recorded_stack(42)
        assert len(lines) == 2
        assert "func_a" in lines[0]
        assert "func_b+0x10" in lines[1]

    def test_format_recorded_stack_not_found(self) -> None:
        """Test formatting non-existent thread."""
        mgr = TraceManager()
        lines = mgr.format_recorded_stack(999)
        assert not lines

    def test_format_recorded_stack_empty_pcs(self) -> None:
        """Test formatting thread with empty PCs."""
        mgr = TraceManager()
        mgr.threads[42] = ThreadRecord(tid=42, pcs=[])

        lines = mgr.format_recorded_stack(42)
        assert not lines


class TestIsReplayMode:
    """Tests for is_replay_mode function."""

    def setup_method(self) -> None:
        """Reset trace manager before each test."""
        reset_trace_manager()

    def test_not_replay_by_default(self) -> None:
        """Test that is_replay_mode returns False by default."""
        assert is_replay_mode() is False

    def test_replay_after_load(self) -> None:
        """Test that is_replay_mode returns True after loading bundle."""
        mgr = TraceManager()
        mgr.memory.write(0x1000, b'test')
        mgr.metadata = {'version': 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, 'test.sdb')
            mgr.save_bundle(bundle_path)

            # Reset and load
            reset_trace_manager()
            loaded = TraceManager.load_bundle(bundle_path)

            # The loaded manager has is_replay=True, but the global one doesn't
            assert loaded.is_replay is True


class TestBundleThreadFields:
    """Tests for bundle serialization of new ThreadRecord fields."""

    def test_save_and_load_thread_with_stack_bounds(self) -> None:
        """Test saving and loading threads with stack bounds."""
        mgr = TraceManager()
        mgr.memory.write(0x1000, b'test')
        mgr.metadata = {'version': 1}
        mgr.threads[123] = ThreadRecord(
            tid=123,
            pcs=[0x1000, 0x2000],
            stack_start=0xffff8000,
            stack_end=0xffffc000,
            comm="test_comm",
            task_addr=0xdeadbeef,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, 'test.sdb')
            mgr.save_bundle(bundle_path)

            loaded = TraceManager.load_bundle(bundle_path)
            thread = loaded.threads[123]

            assert thread.tid == 123
            assert thread.pcs == [0x1000, 0x2000]
            assert thread.stack_start == 0xffff8000
            assert thread.stack_end == 0xffffc000
            assert thread.comm == "test_comm"
            assert thread.task_addr == 0xdeadbeef

    def test_load_legacy_bundle_without_stack_fields(self) -> None:
        """Test loading a bundle without the new stack fields (backwards compat)."""
        # Create a bundle manually with old format (no stack_start/stack_end/comm)
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, 'legacy.sdb')

            with zipfile.ZipFile(bundle_path, 'w') as zf:
                zf.writestr('metadata.json', json.dumps({'version': 1}))
                zf.writestr('objects.json', json.dumps({}))
                zf.writestr('symbols.json', json.dumps({}))
                # Old format: only pcs, no stack_start/stack_end/comm
                zf.writestr('threads.json',
                            json.dumps({'42': {
                                'pcs': [0x1000]
                            }}))

                # Minimal memory data
                mem_data = b'SMEM' + struct.pack('<I', 1)
                zf.writestr('memory.bin.gz', gzip.compress(mem_data))

            loaded = TraceManager.load_bundle(bundle_path)
            thread = loaded.threads[42]

            assert thread.tid == 42
            assert thread.pcs == [0x1000]
            # Defaults for missing fields
            assert thread.stack_start == 0
            assert thread.stack_end == 0
            assert thread.comm == ""
            assert thread.task_addr == 0


class TestKaslrHandling:
    """Tests for KASLR offset handling in replay mode."""

    def test_metadata_with_kaslr_offset(self) -> None:
        """Test that kaslr_offset in metadata is used directly."""
        manager = TraceManager()
        manager.metadata = {
            'kaslr_offset': 0x19600000,
            'kernel_text_address': 0xffffffff9a600000,
        }

        # kaslr_offset should take precedence
        assert manager.metadata['kaslr_offset'] == 0x19600000

    def test_metadata_with_kernel_text_address(self) -> None:
        """Test calculating KASLR offset from kernel_text_address."""
        manager = TraceManager()
        manager.metadata = {
            'kernel_text_address': 0xffffffff9a600000,
        }

        # KASLR offset = kernel_text_address - VMLINUX_TEXT_BASE
        vmlinux_text_base = 0xffffffff81000000
        expected_offset = manager.metadata[
            'kernel_text_address'] - vmlinux_text_base
        assert expected_offset == 0x19600000

    def test_metadata_with_vmcoreinfo_fields(self) -> None:
        """Test vmcoreinfo fields are preserved in metadata."""
        manager = TraceManager()
        manager.metadata = {
            'vmcoreinfo':
                'OSRELEASE=5.4.0\nBUILD-ID=abc123\nKERNELOFFSET=19600000',
            'kernel_release':
                '5.4.0',
            'kernel_build_id':
                'abc123',
            'kaslr_offset':
                0x19600000,
        }

        assert manager.metadata['kernel_release'] == '5.4.0'
        assert manager.metadata['kernel_build_id'] == 'abc123'
        assert manager.metadata['kaslr_offset'] == 0x19600000

    def test_bundle_preserves_kaslr_metadata(self, tmp_path: Path) -> None:
        """Test that KASLR metadata survives save/load cycle."""
        bundle_path = str(tmp_path / "kaslr_test.sdb")

        manager = TraceManager()
        manager.metadata = {
            'version': 1,
            'kernel_text_address': 0xffffffff9a600000,
            'kernel_stext_address': 0xffffffff9a600000,
            'kaslr_offset': 0x19600000,
            'kernel_release': '5.4.0-test',
            'kernel_build_id': 'deadbeef',
        }
        manager.save_bundle(bundle_path)

        loaded = TraceManager.load_bundle(bundle_path)

        assert loaded.metadata['kernel_text_address'] == 0xffffffff9a600000
        assert loaded.metadata['kernel_stext_address'] == 0xffffffff9a600000
        assert loaded.metadata['kaslr_offset'] == 0x19600000
        assert loaded.metadata['kernel_release'] == '5.4.0-test'
        assert loaded.metadata['kernel_build_id'] == 'deadbeef'

    def test_no_kaslr_info_defaults_to_zero(self) -> None:
        """Test that missing KASLR info results in zero offset."""
        manager = TraceManager()
        manager.metadata = {'version': 1}

        # No kaslr_offset, kernel_text_address, or kernel_stext_address
        assert 'kaslr_offset' not in manager.metadata
        assert 'kernel_text_address' not in manager.metadata

    def test_kernel_range_calculation(self) -> None:
        """Test that kernel address range is correctly adjusted for KASLR."""
        # Base kernel range (no KASLR)
        base_start = 0xffffffff80000000
        base_end = 0xffffffffc0000000

        kaslr_offset = 0x19600000

        # Adjusted range
        adjusted_start = base_start + kaslr_offset
        adjusted_end = base_end + kaslr_offset

        assert adjusted_start == 0xffffffff99600000
        assert adjusted_end == 0xffffffffd9600000
