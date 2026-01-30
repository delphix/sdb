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

These tests focus on the SparseMemory class and TraceManager state management.
Integration tests for vmcore recording/replay are in test_session_tracing.py.
"""

import pytest

from sdb.session import (
    SparseMemory,
    MemorySegment,
    TraceManager,
    FAT_READ_ALIGNMENT,
    FAT_READ_MASK,
    VMCORE_EXTENSION,
    SDB_NOTE_SESSION,
    get_trace_manager,
    reset_trace_manager,
    is_replay_mode,
)


class TestSparseMemory:
    """Tests for the SparseMemory class."""

    def test_write_simple(self) -> None:
        """Test basic write operation."""
        mem = SparseMemory()
        data = b'hello world'
        mem.write(0x1000, data)

        segments = mem.get_segments()
        assert len(segments) == 1
        assert segments[0] == (0x1000, data)

    def test_multiple_disjoint_segments(self) -> None:
        """Test multiple non-overlapping segments."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x2000, b'bbbb')
        mem.write(0x3000, b'cccc')

        segments = mem.get_segments()
        assert len(segments) == 3

        # Segments are sorted by address
        assert segments[0] == (0x1000, b'aaaa')
        assert segments[1] == (0x2000, b'bbbb')
        assert segments[2] == (0x3000, b'cccc')

    def test_overlapping_write_merged(self) -> None:
        """Test that overlapping writes are merged in get_segments()."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaaaaaaaa')  # 10 bytes at 0x1000
        mem.write(0x1008, b'BBBB')  # 4 bytes overlapping at 0x1008

        segments = mem.get_segments()
        # Should be merged into one segment
        assert len(segments) == 1
        addr, data = segments[0]
        assert addr == 0x1000
        # Merged: first 8 bytes from first write, last 4 extended by second
        assert len(data) == 12  # 0x1000-0x100b inclusive

    def test_adjacent_segments_merged(self) -> None:
        """Test that adjacent segments are merged."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x1004, b'bbbb')

        segments = mem.get_segments()
        assert len(segments) == 1
        assert segments[0] == (0x1000, b'aaaabbbb')

    def test_get_total_size(self) -> None:
        """Test total size calculation."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x2000, b'bbbbbb')

        assert mem.get_total_size() == 10

    def test_get_segment_count(self) -> None:
        """Test segment count (before merging)."""
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

    def test_empty_segments(self) -> None:
        """Test get_segments on empty memory."""
        mem = SparseMemory()
        assert mem.get_segments() == []

    def test_same_address_overwrites(self) -> None:
        """Test that writing to the same address overwrites."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x1000, b'BBBB')

        # Last write wins (simple dict storage)
        segments = mem.get_segments()
        assert len(segments) == 1
        assert segments[0] == (0x1000, b'BBBB')


class TestMemorySegment:  # pylint: disable=too-few-public-methods
    """Tests for the MemorySegment dataclass."""

    def test_memory_segment(self) -> None:
        """Test MemorySegment dataclass."""
        seg = MemorySegment(address=0x1000, data=b'test')
        assert seg.address == 0x1000
        assert seg.data == b'test'


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
        assert mgr.original_read is None

    def test_get_status_initial(self) -> None:
        """Test status reporting on fresh manager."""
        mgr = TraceManager()
        status = mgr.get_status()
        assert status['is_recording'] is False
        assert status['is_replay'] is False
        assert status['output_path'] is None
        assert status['memory_segments'] == 0
        assert status['memory_size'] == 0

    def test_get_status_with_memory(self) -> None:
        """Test status reporting with memory written."""
        mgr = TraceManager()
        mgr.memory.write(0x1000, b'test data')

        status = mgr.get_status()
        assert status['memory_segments'] == 1
        assert status['memory_size'] == 9

    def test_metadata_defaults(self) -> None:
        """Test metadata is empty dict by default."""
        mgr = TraceManager()
        assert mgr.metadata == {}

    def test_compression_setting(self) -> None:
        """Test compression setting can be configured."""
        mgr = TraceManager()
        # Default compression is zlib
        assert mgr.compression == 'zlib'
        assert mgr.compression_level == 6

        mgr.set_compression('zstd', level=3)
        assert mgr.compression == 'zstd'
        assert mgr.compression_level == 3

    def test_cannot_start_recording_twice(self) -> None:
        """Test that starting recording twice raises error."""
        mgr = TraceManager()
        # Need a mock program for this
        # This test verifies the state check exists
        mgr.is_recording = True

        with pytest.raises(RuntimeError, match="Recording already in progress"):
            # We can't easily test this without a real drgn.Program
            # but we can verify the flag check by setting it manually
            mgr.start_recording(None, "test.vmcore")

    def test_cannot_record_in_replay_mode(self) -> None:
        """Test that recording in replay mode raises error."""
        mgr = TraceManager()
        mgr.is_replay = True

        with pytest.raises(RuntimeError,
                           match="Cannot record while in replay mode"):
            mgr.start_recording(None, "test.vmcore")

    def test_stop_recording_without_start(self) -> None:
        """Test stopping recording without starting raises error."""
        mgr = TraceManager()

        with pytest.raises(RuntimeError, match="No recording in progress"):
            mgr.stop_recording(None)

    def test_trace_read_without_recording(self) -> None:
        """Test trace_read without recording raises error."""
        mgr = TraceManager()

        with pytest.raises(RuntimeError, match="No recording in progress"):
            mgr.trace_read(0x1000, 100)

    def test_capture_object_without_recording(self) -> None:
        """Test capture_object without recording is a no-op."""
        mgr = TraceManager()
        # Should not raise, just silently return
        mgr.capture_object(None, depth=1)


class TestFatReadAlignment:
    """Tests for fat read alignment constants."""

    def test_fat_read_alignment_constant(self) -> None:
        """Test that fat read alignment is 256 bytes as designed."""
        assert FAT_READ_ALIGNMENT == 256

    def test_alignment_mask(self) -> None:
        """Test alignment calculation."""
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


class TestIsReplayMode:
    """Tests for is_replay_mode function."""

    def setup_method(self) -> None:
        """Reset trace manager before each test."""
        reset_trace_manager()

    def test_not_replay_by_default(self) -> None:
        """Test that is_replay_mode returns False by default."""
        assert is_replay_mode() is False

    def test_replay_when_set(self) -> None:
        """Test that is_replay_mode returns True when set."""
        mgr = get_trace_manager()
        mgr.is_replay = True
        assert is_replay_mode() is True


class TestConstants:
    """Tests for module constants."""

    def test_vmcore_extension(self) -> None:
        """Test vmcore extension constant."""
        assert VMCORE_EXTENSION == '.vmcore.recorded'

    def test_sdb_note_session(self) -> None:
        """Test SDB note type constant."""
        assert SDB_NOTE_SESSION == 259


class TestSparseMemoryMerging:
    """Tests for SparseMemory segment merging behavior."""

    def test_completely_contained_segment(self) -> None:
        """Test that a segment contained within another is handled."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaaaaaaaa')  # 10 bytes
        mem.write(0x1002, b'BB')  # Contained within

        segments = mem.get_segments()
        # The contained segment should not extend the merged result
        assert len(segments) == 1
        addr, data = segments[0]
        assert addr == 0x1000
        assert len(data) == 10

    def test_gap_between_segments(self) -> None:
        """Test that gaps between segments are preserved."""
        mem = SparseMemory()
        mem.write(0x1000, b'aaaa')
        mem.write(0x2000, b'bbbb')  # Gap between

        segments = mem.get_segments()
        assert len(segments) == 2
        assert segments[0][0] == 0x1000
        assert segments[1][0] == 0x2000

    def test_multiple_adjacent_merges(self) -> None:
        """Test merging multiple adjacent segments."""
        mem = SparseMemory()
        mem.write(0x1000, b'aa')
        mem.write(0x1002, b'bb')
        mem.write(0x1004, b'cc')
        mem.write(0x1006, b'dd')

        segments = mem.get_segments()
        assert len(segments) == 1
        assert segments[0] == (0x1000, b'aabbccdd')
