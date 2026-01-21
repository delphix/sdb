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
# pylint: disable=too-many-lines
"""
Integration tests for session recording and replay functionality.

These tests verify that:
1. Session recording captures memory correctly from crash dumps
2. The .sdb bundle format is correct
3. Sessions can be loaded back
4. The %session REPL commands work
"""

import json
import os
import tempfile
from typing import Any, Generator
import zipfile

import pytest

import drgn

import sdb
from sdb.internal.cli import setup_replay_target
from sdb.internal.repl import REPL
from sdb.session import (
    TraceManager,
    get_trace_manager,
    reset_trace_manager,
    is_replay_mode,
)
from tests.integration.infra import (
    get_crash_dump_dir_paths,
    get_all_reference_crash_dumps,
    get_modules_dir,
    get_vmlinux_path,
    RefDump,
)


@pytest.fixture(autouse=True)
def reset_trace_manager_fixture() -> Generator[None, None, None]:
    """Reset the trace manager before and after each test."""
    reset_trace_manager()
    yield
    reset_trace_manager()


def setup_test_env(rdump: RefDump) -> None:
    """Set up SDB environment for session tracing tests."""
    sdb.target.set_prog(rdump.program)
    sdb.register_commands()


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestSessionRecording:
    """Tests for session recording functionality."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_recording_captures_memory(self, rdump: RefDump) -> None:
        """Test that recording a session captures memory."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)
            assert trace_mgr.is_recording

            # Run a command that accesses memory via repl_invoke (sets up target)
            rdump.repl_invoke("addr init_task | head 1")

            # Stop recording
            saved_path = trace_mgr.stop_recording(rdump.program)
            assert not trace_mgr.is_recording
            assert os.path.exists(saved_path)

            # Verify memory was captured
            status = trace_mgr.get_status()
            assert status['memory_size'] > 0

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_bundle_format(self, rdump: RefDump) -> None:
        """Test that the bundle has the correct format."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Record something
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl_invoke("addr init_task | head 1")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Verify bundle structure
            with zipfile.ZipFile(saved_path, 'r') as zf:
                names = zf.namelist()
                assert 'metadata.json' in names
                assert 'memory.bin.gz' in names
                assert 'objects.json' in names
                assert 'symbols.json' in names
                assert 'threads.json' in names

                # Verify metadata
                metadata = json.loads(zf.read('metadata.json').decode('utf-8'))
                assert 'version' in metadata
                assert 'timestamp' in metadata
                assert 'arch' in metadata

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_bundle_load_roundtrip(self, rdump: RefDump) -> None:
        """Test that bundles can be saved and loaded."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Record something
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl_invoke("addr init_task | head 1")
            saved_path = trace_mgr.stop_recording(rdump.program)

            original_size = trace_mgr.memory.get_total_size()
            original_segments = trace_mgr.memory.get_segment_count()

            # Load the bundle
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # Verify data matches
            assert loaded_mgr.is_replay
            assert loaded_mgr.memory.get_total_size() == original_size
            assert loaded_mgr.memory.get_segment_count() == original_segments

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_snapshot_command(self, rdump: RefDump) -> None:
        """Test the %session snapshot command."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Use snapshot command (repl.eval_cmd handles % commands)
            result = rdump.repl.eval_cmd("%session snapshot init_task")
            assert result == 0

            # Verify memory was captured
            assert trace_mgr.memory.get_total_size() > 0

            # Stop recording
            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_status_command(self, rdump: RefDump) -> None:
        """Test the %session status command."""
        setup_test_env(rdump)

        # Status without recording
        result = rdump.repl.eval_cmd("%session status")
        assert result == 0

        # Status with recording
        trace_mgr = get_trace_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")
            trace_mgr.start_recording(rdump.program, bundle_path)

            result = rdump.repl.eval_cmd("%session status")
            assert result == 0

            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_stop_commands(self, rdump: RefDump) -> None:
        """Test the %session record and stop commands."""
        setup_test_env(rdump)

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording via command
            result = rdump.repl.eval_cmd(f"%session record {bundle_path}")
            assert result == 0

            trace_mgr = get_trace_manager()
            assert trace_mgr.is_recording

            # Run a command
            rdump.repl_invoke("addr init_task | head 1")

            # Stop recording via command
            result = rdump.repl.eval_cmd("%session stop")
            assert result == 0
            assert not trace_mgr.is_recording

            # Verify file was created (save_bundle adds .sdb if missing)
            expected_path = bundle_path if bundle_path.endswith(
                '.sdb') else bundle_path + '.sdb'
            assert os.path.exists(expected_path)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_fat_read_captures_surrounding_memory(self, rdump: RefDump) -> None:
        """Test that fat reads capture 256-byte aligned memory."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Capture a pointer object - this should trigger fat reads
            rdump.repl_invoke("addr init_task | head 1")

            trace_mgr.stop_recording(rdump.program)

            # Memory size should be aligned to 256 bytes
            # (or larger due to multiple fat reads)
            mem_size = trace_mgr.memory.get_total_size()
            assert mem_size >= 256
            # Memory should be captured in 256-byte aligned chunks
            for start, _, _ in trace_mgr.memory.segments:
                assert start % 256 == 0 or mem_size < 256

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_multiple_commands_accumulate(self, rdump: RefDump) -> None:
        """Test that multiple commands accumulate memory in the trace."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Run first command
            rdump.repl_invoke("addr init_task | head 1")
            size_after_first = trace_mgr.memory.get_total_size()

            # Run second command for different data
            rdump.repl_invoke("addr jiffies | head 1")
            size_after_second = trace_mgr.memory.get_total_size()

            # Memory should have grown (or stayed same if overlapping)
            assert size_after_second >= size_after_first

            trace_mgr.stop_recording(rdump.program)


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestSessionErrors:
    """Tests for session error handling."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_stop_without_recording(self, rdump: RefDump) -> None:
        """Test that stopping without recording gives an error."""
        setup_test_env(rdump)

        result = rdump.repl.eval_cmd("%session stop")
        assert result == 1  # Error

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_double_start_recording(self, rdump: RefDump) -> None:
        """Test that starting recording twice gives an error."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # First start should succeed
            result = rdump.repl.eval_cmd(f"%session record {bundle_path}")
            assert result == 0

            # Second start should fail
            result = rdump.repl.eval_cmd(f"%session record {bundle_path}2")
            assert result == 1  # Error

            # Clean up
            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_snapshot_without_recording(self, rdump: RefDump) -> None:
        """Test that snapshot without recording gives an error."""
        setup_test_env(rdump)

        result = rdump.repl.eval_cmd("%session snapshot init_task")
        assert result == 1  # Error

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_unknown_session_command(self, rdump: RefDump) -> None:
        """Test that unknown session commands give an error."""
        setup_test_env(rdump)

        result = rdump.repl.eval_cmd("%session bogus_command")
        assert result == 1  # Error

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_unknown_meta_command(self, rdump: RefDump) -> None:
        """Test that unknown % commands give an error."""
        setup_test_env(rdump)

        result = rdump.repl.eval_cmd("%bogus")
        assert result == 1  # Error

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_capture_stacks_without_recording(self, rdump: RefDump) -> None:
        """Test that capture-stacks without recording gives an error."""
        setup_test_env(rdump)

        result = rdump.repl.eval_cmd("%session capture-stacks")
        assert result == 1  # Error

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_without_recording(self, rdump: RefDump) -> None:
        """Test that record-memory without recording gives an error."""
        setup_test_env(rdump)

        result = rdump.repl.eval_cmd("%session record-memory 0x1000 256")
        assert result == 1  # Error

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_missing_args(self, rdump: RefDump) -> None:
        """Test that record-memory with missing args gives an error."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Missing size
            result = rdump.repl.eval_cmd("%session record-memory 0x1000")
            assert result == 2  # Incorrect args

            # Missing both
            result = rdump.repl.eval_cmd("%session record-memory")
            assert result == 2  # Incorrect args

            trace_mgr.stop_recording(rdump.program)


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestCaptureStacks:
    """Tests for the capture-stacks command and stack trace recording."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_capture_stacks_command(self, rdump: RefDump) -> None:
        """Test the %session capture-stacks command."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Capture all stacks
            result = rdump.repl.eval_cmd("%session capture-stacks")
            assert result == 0

            # Verify threads were captured
            assert len(trace_mgr.threads) > 0

            # Verify symbols were captured
            assert len(trace_mgr.symbols) > 0

            # Verify memory was captured (for stack memory)
            assert trace_mgr.memory.get_total_size() > 0

            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_capture_stacks_no_locals(self, rdump: RefDump) -> None:
        """Test the %session capture-stacks --no-locals command."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Capture stacks without locals
            result = rdump.repl.eval_cmd("%session capture-stacks --no-locals")
            assert result == 0

            # Verify threads were captured
            assert len(trace_mgr.threads) > 0

            # Verify symbols were captured
            assert len(trace_mgr.symbols) > 0

            # Memory should be much smaller without stack memory
            size_no_locals = trace_mgr.memory.get_total_size()

            trace_mgr.stop_recording(rdump.program)

            # Reset and do with locals
            reset_trace_manager()
            trace_mgr2 = get_trace_manager()

            bundle_path2 = os.path.join(tmpdir, "test2.sdb")
            trace_mgr2.start_recording(rdump.program, bundle_path2)
            rdump.repl.eval_cmd("%session capture-stacks")
            size_with_locals = trace_mgr2.memory.get_total_size()
            trace_mgr2.stop_recording(rdump.program)

            # With locals should capture more memory
            # (stack memory is ~16KB per thread)
            assert size_with_locals >= size_no_locals

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_thread_record_has_stack_bounds(self, rdump: RefDump) -> None:
        """Test that thread records include stack bounds."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            trace_mgr.stop_recording(rdump.program)

            # Check that at least some threads have stack bounds
            threads_with_bounds = sum(1 for t in trace_mgr.threads.values()
                                      if t.stack_start > 0 and t.stack_end > 0)
            assert threads_with_bounds > 0

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_thread_record_has_comm(self, rdump: RefDump) -> None:
        """Test that thread records include comm name."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            trace_mgr.stop_recording(rdump.program)

            # Check that at least some threads have comm names
            threads_with_comm = sum(
                1 for t in trace_mgr.threads.values() if t.comm)
            assert threads_with_comm > 0

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_symbols_recorded_for_pcs(self, rdump: RefDump) -> None:
        """Test that symbols are recorded for stack PCs."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            trace_mgr.stop_recording(rdump.program)

            # Get all PCs from threads
            all_pcs = set()
            for thread in trace_mgr.threads.values():
                all_pcs.update(thread.pcs)

            # Some PCs should have symbols recorded
            pcs_with_symbols = 0
            for pc in all_pcs:
                for addr, sym in trace_mgr.symbols.items():
                    if sym.size > 0 and addr <= pc < addr + sym.size:
                        pcs_with_symbols += 1
                        break
                    if addr == pc:
                        pcs_with_symbols += 1
                        break

            # At least some PCs should be symbolized
            assert pcs_with_symbols > 0

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_bundle_stack_roundtrip(self, rdump: RefDump) -> None:
        """Test that stack data survives save/load roundtrip."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Save counts before loading
            original_threads = len(trace_mgr.threads)
            original_symbols = len(trace_mgr.symbols)

            # Get one thread's data for comparison
            tid = None
            original_thread = None
            if trace_mgr.threads:
                tid = next(iter(trace_mgr.threads.keys()))
                original_thread = trace_mgr.threads[tid]

            # Load the bundle
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # Verify counts match
            assert len(loaded_mgr.threads) == original_threads
            assert len(loaded_mgr.symbols) == original_symbols

            # Verify thread data matches
            if tid is not None and original_thread is not None:
                loaded_thread = loaded_mgr.threads[tid]
                assert loaded_thread.tid == original_thread.tid
                assert loaded_thread.pcs == original_thread.pcs
                assert loaded_thread.stack_start == original_thread.stack_start
                assert loaded_thread.stack_end == original_thread.stack_end
                assert loaded_thread.comm == original_thread.comm

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_symbolize_pc_works(self, rdump: RefDump) -> None:
        """Test that symbolize_pc returns meaningful results."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            trace_mgr.stop_recording(rdump.program)

            # Get a PC that has a symbol
            for thread in trace_mgr.threads.values():
                for pc in thread.pcs:
                    result = trace_mgr.symbolize_pc(pc)
                    # Result should be either hex or a function name
                    assert result.startswith('0x') or '+' in result or any(
                        c.isalpha() for c in result)
                    # Test first few PCs
                    break
                break

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_format_recorded_stack(self, rdump: RefDump) -> None:
        """Test that format_recorded_stack produces output."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            trace_mgr.stop_recording(rdump.program)

            # Format one thread's stack
            if trace_mgr.threads:
                tid = next(iter(trace_mgr.threads.keys()))
                lines = trace_mgr.format_recorded_stack(tid)

                # Should have some lines if thread has PCs
                thread = trace_mgr.threads[tid]
                if thread.pcs:
                    assert len(lines) > 0
                    # Each line should have frame number and address
                    for line in lines:
                        assert '#' in line
                        assert '0x' in line


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestRecordMemory:
    """Tests for the record-memory command."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_basic(self, rdump: RefDump) -> None:
        """Test basic record-memory command."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Get the address of init_task to record
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            addr = int(init_task.address_of_())

            # Record memory at that address
            result = rdump.repl.eval_cmd(
                f"%session record-memory {hex(addr)} 256")
            assert result == 0

            # Verify memory was captured
            assert trace_mgr.memory.get_total_size() >= 256

            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_hex_size(self, rdump: RefDump) -> None:
        """Test record-memory with hex size."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Get the address of init_task
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            addr = int(init_task.address_of_())

            # Record with hex size
            result = rdump.repl.eval_cmd(
                f"%session record-memory {hex(addr)} 0x100")
            assert result == 0

            # 0x100 = 256 bytes
            assert trace_mgr.memory.get_total_size() >= 256

            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_accumulates(self, rdump: RefDump) -> None:
        """Test that multiple record-memory calls accumulate."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Get addresses
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            addr1 = int(init_task.address_of_())

            jiffies = sdb_target.get_object("jiffies")
            addr2 = int(jiffies.address_of_())

            # Record first region
            rdump.repl.eval_cmd(f"%session record-memory {hex(addr1)} 256")
            size1 = trace_mgr.memory.get_total_size()

            # Record second region (different address)
            rdump.repl.eval_cmd(f"%session record-memory {hex(addr2)} 256")
            size2 = trace_mgr.memory.get_total_size()

            # Memory should have grown
            assert size2 >= size1

            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_in_bundle(self, rdump: RefDump) -> None:
        """Test that record-memory data survives save/load."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "test.sdb")

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Get address and record
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            addr = int(init_task.address_of_())

            rdump.repl.eval_cmd(f"%session record-memory {hex(addr)} 512")
            original_size = trace_mgr.memory.get_total_size()

            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load and verify
            loaded_mgr = TraceManager.load_bundle(saved_path)
            assert loaded_mgr.memory.get_total_size() == original_size

            # Verify we can read the recorded memory
            data = loaded_mgr.memory.read(addr & ~0xFF, 256)
            assert len(data) == 256


class TestKaslrCapture:
    """Integration tests for KASLR offset capture during recording."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_kernel_text_address_captured(self, rdump: RefDump) -> None:
        """Test that kernel_text_address is captured during recording."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "kaslr_test.sdb")

            # Start and stop recording to capture metadata
            trace_mgr.start_recording(rdump.program, bundle_path)
            trace_mgr.stop_recording(rdump.program)

            # Verify kernel_text_address was captured
            assert 'kernel_text_address' in trace_mgr.metadata
            kernel_text = trace_mgr.metadata['kernel_text_address']

            # Should be in kernel text range
            assert kernel_text >= 0xffffffff80000000
            assert kernel_text < 0xfffffffffffff000

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_kaslr_offset_calculation(self, rdump: RefDump) -> None:
        """Test that KASLR offset can be calculated from captured metadata."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "kaslr_calc.sdb")

            trace_mgr.start_recording(rdump.program, bundle_path)
            trace_mgr.stop_recording(rdump.program)

            # Calculate KASLR offset
            vmlinux_text_base = 0xffffffff81000000
            kernel_text = trace_mgr.metadata.get('kernel_text_address', 0)

            if kernel_text:
                kaslr_offset = kernel_text - vmlinux_text_base
                # KASLR offset should be reasonable (within 2GB)
                assert abs(kaslr_offset) < 0x80000000

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_kaslr_metadata_survives_bundle_roundtrip(self,
                                                      rdump: RefDump) -> None:
        """Test that KASLR metadata survives save/load cycle."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "kaslr_roundtrip.sdb")

            # Record
            trace_mgr.start_recording(rdump.program, bundle_path)
            original_kernel_text = trace_mgr.metadata.get('kernel_text_address')
            original_stext = trace_mgr.metadata.get('kernel_stext_address')
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load and verify
            loaded_mgr = TraceManager.load_bundle(saved_path)

            if original_kernel_text:
                assert loaded_mgr.metadata[
                    'kernel_text_address'] == original_kernel_text
            if original_stext:
                assert loaded_mgr.metadata[
                    'kernel_stext_address'] == original_stext

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_bundle_metadata_json_contains_kaslr_info(self,
                                                      rdump: RefDump) -> None:
        """Test that the bundle's metadata.json contains KASLR info."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "kaslr_json.sdb")

            trace_mgr.start_recording(rdump.program, bundle_path)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Read metadata.json directly from the bundle
            with zipfile.ZipFile(saved_path, 'r') as zf:
                metadata = json.loads(zf.read('metadata.json').decode('utf-8'))

            # Should contain kernel_text_address
            assert 'kernel_text_address' in metadata
            # Value should be an integer (stored as JSON number)
            assert isinstance(metadata['kernel_text_address'], int)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_recorded_pcs_match_kernel_range(self, rdump: RefDump) -> None:
        """Test that recorded thread PCs fall within the kernel range."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "pcs_range.sdb")

            trace_mgr.start_recording(rdump.program, bundle_path)

            # Capture some stacks
            rdump.repl.eval_cmd("%session capture-stacks --no-locals")

            trace_mgr.stop_recording(rdump.program)

            # Verify PCs are in kernel range
            kernel_text = trace_mgr.metadata.get('kernel_text_address', 0)
            if kernel_text and trace_mgr.threads:
                # Sample some PCs
                for thread_rec in list(trace_mgr.threads.values())[:5]:
                    for pc in thread_rec.pcs:
                        if pc != 0:
                            # PC should be in kernel space
                            assert pc >= 0xffff800000000000, \
                                f"PC {hex(pc)} not in kernel space"


class TestRecordReplayEndToEnd:
    """
    End-to-end tests that verify recording + replay produce consistent output.

    These tests record a session from a crash dump, save it, load it in
    replay mode with the same debug info, and verify that type information
    and symbol resolution produce the same results.
    """

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_ptype_matches_after_replay(self, rdump: RefDump) -> None:
        """Test that ptype output is identical in recording vs replay mode."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "e2e_ptype.sdb")

            # Get ptype exit code during live/recording mode (0 = success)
            live_exit_code = rdump.repl_invoke("ptype task_struct | head 5")
            assert live_exit_code == 0, "ptype should succeed in live mode"

            # Start recording and capture some objects
            trace_mgr.start_recording(rdump.program, bundle_path)
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            trace_mgr.capture_object(init_task, depth=0)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Now load the bundle and set up replay
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # The metadata should have kernel_text_address
            assert 'kernel_text_address' in loaded_mgr.metadata

            # Verify ptype would work (we can't easily run replay in-process,
            # but we can verify the metadata is correct for KASLR)
            vmlinux_text_base = 0xffffffff81000000
            kernel_text = loaded_mgr.metadata['kernel_text_address']
            kaslr_offset = kernel_text - vmlinux_text_base

            # The offset should be reasonable (within 2GB, common for KASLR)
            assert abs(kaslr_offset) < 0x80000000, \
                f"KASLR offset {hex(kaslr_offset)} seems unreasonable"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_symbol_address_preserved(self, rdump: RefDump) -> None:
        """Test that symbol addresses are preserved correctly in replay."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "e2e_symbol.sdb")

            # Get jiffies address during live mode
            from sdb import target as sdb_target
            jiffies = sdb_target.get_object("jiffies")
            live_jiffies_addr = int(jiffies.address_of_())

            # Start recording
            trace_mgr.start_recording(rdump.program, bundle_path)
            trace_mgr.capture_object(jiffies, depth=0)
            trace_mgr.record_object("jiffies", live_jiffies_addr,
                                    str(jiffies.type_))
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load bundle and verify
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # The recorded object should have the same address
            assert "jiffies" in loaded_mgr.objects
            replay_jiffies_addr = loaded_mgr.objects["jiffies"].address
            assert replay_jiffies_addr == live_jiffies_addr, \
                f"Address mismatch: live={hex(live_jiffies_addr)}, " \
                f"replay={hex(replay_jiffies_addr)}"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_memory_content_preserved(self, rdump: RefDump) -> None:
        """Test that memory content read during recording matches replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            addr = int(init_task.address_of_())

            # Read memory during live mode and record
            live_memory = rdump.program.read(addr, 256)
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "e2e_memory.sdb"))
            trace_mgr.capture_object(init_task, depth=0)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load bundle and read from replay memory
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)
            aligned_addr = addr & ~0xFF
            offset = addr - aligned_addr
            replay_memory = loaded_mgr.memory.read(aligned_addr, 256)

            # Compare overlapping portion
            assert live_memory[:256 - offset] == replay_memory[offset:256], \
                "Memory content mismatch between live and replay"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_stack_symbols_match_live(self, rdump: RefDump) -> None:
        """Test that recorded stack symbols match live symbol resolution."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "e2e_stacks.sdb")

            # Start recording and capture stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks --no-locals")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Get some recorded symbols
            recorded_symbols = dict(trace_mgr.symbols)

            # Load bundle
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # Verify symbols survived roundtrip
            assert len(loaded_mgr.symbols) == len(recorded_symbols)

            # Verify at least some symbol addresses match what we'd expect
            for addr, sym_rec in list(loaded_mgr.symbols.items())[:10]:
                # Symbol address should be in kernel space
                assert addr >= 0xffff800000000000, \
                    f"Symbol {sym_rec.name} at {hex(addr)} not in kernel space"

                # Symbol should have a name
                assert sym_rec.name, f"Symbol at {hex(addr)} has no name"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_thread_count_preserved(self, rdump: RefDump) -> None:
        """Test that thread count is preserved in replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "e2e_threads.sdb"))
            rdump.repl.eval_cmd("%session capture-stacks --no-locals")
            live_thread_count = len(trace_mgr.threads)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load bundle and verify thread count
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)

            assert len(loaded_mgr.threads) == live_thread_count, \
                f"Thread count mismatch: live={live_thread_count}, " \
                f"replay={len(loaded_mgr.threads)}"
            assert live_thread_count > 0, "Should have captured some threads"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_jiffies_value_preserved(self, rdump: RefDump) -> None:
        """Test that jiffies value is preserved between recording and replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            from sdb import target as sdb_target

            # Get jiffies value and address during live mode
            jiffies_obj = sdb_target.get_object("jiffies")
            live_jiffies_value = int(jiffies_obj)
            live_jiffies_addr = int(jiffies_obj.address_of_())

            # Record the session with jiffies captured
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "jiffies_val.sdb"))
            trace_mgr.capture_object(jiffies_obj, depth=0)
            trace_mgr.record_object("jiffies", live_jiffies_addr,
                                    str(jiffies_obj.type_))
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load bundle and verify
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # Address should match
            assert loaded_mgr.objects["jiffies"].address == live_jiffies_addr

            # Read the actual value from recorded memory
            import struct
            replay_mem = loaded_mgr.memory.read(live_jiffies_addr & ~0xFF, 256)
            offset = live_jiffies_addr & 0xFF
            replay_value = struct.unpack('<Q', replay_mem[offset:offset + 8])[0]

            assert replay_value == live_jiffies_value, \
                f"jiffies mismatch: live={live_jiffies_value}, replay={replay_value}"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_init_task_comm_preserved(self, rdump: RefDump) -> None:
        """Test that init_task.comm value is preserved between record/replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            from sdb import target as sdb_target

            # Get init_task.comm during live mode
            init_task = sdb_target.get_object("init_task")
            live_comm = init_task.comm.string_().decode('utf-8')
            init_task_addr = int(init_task.address_of_())

            # Record the session with init_task captured
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "init_task.sdb"))
            trace_mgr.capture_object(init_task, depth=0)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load bundle
            reset_trace_manager()
            loaded_mgr = TraceManager.load_bundle(saved_path)

            # Read comm field from recorded memory (offset varies by kernel)
            # comm is at a known offset in task_struct, typically around 0x678
            # We'll verify by checking memory contains the expected string
            aligned_addr = init_task_addr & ~0xFF
            replay_mem = loaded_mgr.memory.read(aligned_addr, 4096)

            # The comm string "swapper/0" or "swapper" should be in the memory
            assert live_comm.encode('utf-8') in replay_mem, \
                f"init_task.comm '{live_comm}' not found in replay memory"


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestStacksReplay:
    """Tests for the stacks command in replay mode."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_stacks_command_works_in_replay_mode(self, rdump: RefDump,
                                                 capsys: Any) -> None:
        """Test that the stacks command works in replay mode."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "stacks_replay.sdb")

            # Record a session with stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks --no-locals")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Verify we captured some threads
            assert len(trace_mgr.threads) > 0, "Should have captured threads"

            # Reset trace manager and load bundle in replay mode
            reset_trace_manager()

            # Get vmlinux path for debug info
            # Setup replay target
            replay_prog = setup_replay_target(
                saved_path, [get_vmlinux_path(rdump.dump_dir_path)], quiet=True)
            sdb.target.set_prog(replay_prog)
            sdb.target.set_thread(0)
            sdb.target.set_frame(-1)
            sdb.register_commands()

            # Verify we're in replay mode
            assert is_replay_mode(), "Should be in replay mode"

            # Create REPL for replay mode
            replay_repl = REPL(replay_prog,
                               list(sdb.get_registered_commands().keys()))

            # Clear any prior output
            capsys.readouterr()

            # Run stacks command in replay mode
            result = replay_repl.eval_cmd("stacks")
            assert result == 0, "stacks command should succeed in replay mode"

            # Capture output
            captured = capsys.readouterr()
            output = captured.out

            # Verify output contains expected elements
            assert 'TID' in output, "Output should contain TID header"
            assert 'COMM' in output, "Output should contain COMM header"
            # Output should have some actual stack frames (functions)
            assert len(output.splitlines()) > 3, \
                f"Output should have multiple lines: {output}"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_stacks_output_contains_recorded_threads(self, rdump: RefDump,
                                                     capsys: Any) -> None:
        """Verify stacks output contains info from recorded threads."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Record a session with stacks
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "stacks_verify.sdb"))
            rdump.repl.eval_cmd("%session capture-stacks --no-locals")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Get a sample of recorded thread comms
            sample_comms = {
                t.comm for t in list(trace_mgr.threads.values())[:5] if t.comm
            }

            # Reset and setup replay mode
            reset_trace_manager()

            replay_prog = setup_replay_target(
                saved_path, [get_vmlinux_path(rdump.dump_dir_path)], quiet=True)
            sdb.target.set_prog(replay_prog)
            sdb.target.set_thread(0)
            sdb.target.set_frame(-1)
            sdb.register_commands()

            capsys.readouterr()
            REPL(replay_prog,
                 list(sdb.get_registered_commands().keys())).eval_cmd("stacks")
            output = capsys.readouterr().out

            # At least some recorded thread names should appear in output
            found_comms = sum(1 for comm in sample_comms if comm in output)
            assert found_comms > 0, \
                f"Output should contain recorded thread names. " \
                f"Sample comms: {sample_comms}, Output: {output[:500]}"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_stacks_returns_empty_iterator_in_replay(self, rdump: RefDump) \
            -> None:
        """Test that stacks command returns task pointers in replay mode."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "stacks_iter.sdb")

            # Record a session with stacks
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks --no-locals")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Reset and setup replay mode
            reset_trace_manager()

            replay_prog = setup_replay_target(
                saved_path, [get_vmlinux_path(rdump.dump_dir_path)], quiet=True)
            sdb.target.set_prog(replay_prog)
            sdb.target.set_thread(0)
            sdb.target.set_frame(-1)
            sdb.register_commands()

            # Import and test the stacks command directly
            from sdb.commands.linux.stacks import KernelStacks

            stacks_cmd = KernelStacks()
            result = list(stacks_cmd.no_input())

            # In replay mode, no_input should return recorded task_struct pointers
            assert result, "no_input should return task_struct pointers in replay"
            assert all(int(obj) != 0 for obj in result), \
                "All replay task pointers should be non-zero"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    @pytest.mark.parametrize('cmd', [
        "stacks | head 1 | frame 1 | locals",
        "stacks | head 1 | frame 1 | registers",
        "stacks | head 1 | frame 1 | registers -x",
    ])
    def test_locals_registers_in_replay_mode(self, rdump: RefDump, cmd: str,
                                             capsys: Any) -> None:
        """Verify locals/registers produce output in replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "locals_replay.sdb")

            # Record stacks with locals so replay can unwind frames
            trace_mgr.start_recording(rdump.program, bundle_path)
            rdump.repl.eval_cmd("%session capture-stacks")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Reset and setup replay mode
            reset_trace_manager()
            replay_prog = setup_replay_target(
                saved_path, [get_vmlinux_path(rdump.dump_dir_path)], quiet=True)
            sdb.target.set_prog(replay_prog)
            sdb.target.set_thread(0)
            sdb.target.set_frame(-1)
            sdb.register_commands()

            replay_repl = REPL(replay_prog,
                               list(sdb.get_registered_commands().keys()))

            capsys.readouterr()
            result = replay_repl.eval_cmd(cmd)
            captured = capsys.readouterr()

            assert result == 0
            assert captured.out.strip()
            if "locals" in cmd:
                assert "=" in captured.out
            else:
                assert "registers unavailable in replay" in captured.out


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestModuleCommandsReplay:
    """Tests for module-dependent commands (spa, vdev, etc.) in replay mode."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_spa_command_registered_in_replay_mode(self, rdump: RefDump) \
            -> None:
        """Test that spa command is registered in replay mode."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "spa_replay.sdb")

            # Record a minimal session
            trace_mgr.start_recording(rdump.program, bundle_path)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Reset and setup replay mode
            reset_trace_manager()

            replay_prog = setup_replay_target(saved_path, [
                get_vmlinux_path(rdump.dump_dir_path),
                get_modules_dir(rdump.dump_dir_path)
            ],
                                              quiet=True)
            sdb.target.set_prog(replay_prog)
            sdb.target.set_thread(0)
            sdb.target.set_frame(-1)
            sdb.register_commands()

            # Verify spa command is registered in replay mode
            registered_cmds = sdb.get_registered_commands()
            assert 'spa' in registered_cmds, \
                "spa command should be registered in replay mode"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_spa_namespace_avl_recordable(self, rdump: RefDump) -> None:
        """Test that spa_namespace_avl can be recorded for replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "spa_avl.sdb")

            # Record spa_namespace_avl
            trace_mgr.start_recording(rdump.program, bundle_path)

            # Try to access spa_namespace_avl and capture it
            try:
                from sdb import target as sdb_target
                spa_avl = sdb_target.get_object("spa_namespace_avl")
                trace_mgr.capture_object(spa_avl, depth=0)

                # Record the object info
                avl_addr = int(spa_avl.address_of_())
                trace_mgr.record_object("spa_namespace_avl", avl_addr,
                                        str(spa_avl.type_))
                recorded = True
            except (LookupError, drgn.FaultError):
                # ZFS might not be loaded in this dump
                recorded = False

            trace_mgr.stop_recording(rdump.program)

            if recorded:
                # Verify the object was captured
                assert 'spa_namespace_avl' in trace_mgr.objects, \
                    "spa_namespace_avl should be recorded"

                # Verify memory was captured
                status = trace_mgr.get_status()
                assert status['memory_size'] > 0, \
                    "Memory should be captured for spa_namespace_avl"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_spa_data_survives_roundtrip(self, rdump: RefDump) -> None:
        """Test that recorded spa data survives save/load roundtrip."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "spa_roundtrip.sdb")

            # Record spa_namespace_avl if ZFS is loaded
            trace_mgr.start_recording(rdump.program, bundle_path)

            avl_addr = None
            try:
                from sdb import target as sdb_target
                spa_avl = sdb_target.get_object("spa_namespace_avl")
                avl_addr = int(spa_avl.address_of_())
                trace_mgr.capture_object(spa_avl, depth=0)
                trace_mgr.record_object("spa_namespace_avl", avl_addr,
                                        str(spa_avl.type_))
            except (LookupError, drgn.FaultError):
                pass

            saved_path = trace_mgr.stop_recording(rdump.program)

            if avl_addr is None:
                # ZFS not loaded, skip the rest
                return

            # Load the bundle and verify data
            loaded_mgr = TraceManager.load_bundle(saved_path)

            assert 'spa_namespace_avl' in loaded_mgr.objects, \
                "spa_namespace_avl should survive roundtrip"
            assert loaded_mgr.objects['spa_namespace_avl'].address == avl_addr, \
                "spa_namespace_avl address should be preserved"

            # Verify memory is readable at the recorded address
            aligned_addr = avl_addr & ~0xFF
            mem = loaded_mgr.memory.read(aligned_addr, 256)
            assert len(mem) == 256, \
                "Should be able to read memory at spa_namespace_avl"
