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
