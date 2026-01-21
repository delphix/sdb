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
from typing import Generator
import zipfile

import pytest

import sdb
from sdb.session import (
    TraceManager,
    get_trace_manager,
    reset_trace_manager,
)
from tests.integration.infra import (
    get_crash_dump_dir_paths,
    get_all_reference_crash_dumps,
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
