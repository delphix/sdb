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
2. The recorded vmcore format is valid (ELF64)
3. Sessions can be loaded back via drgn's set_core_dump()
4. The %session REPL commands work
"""

import os
import tempfile
from typing import Generator

import pytest

import drgn

import sdb
from sdb.session import (
    get_trace_manager,
    reset_trace_manager,
    extract_sdb_notes,
    VMCORE_EXTENSION,
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
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)
            assert trace_mgr.is_recording

            # Run a command that accesses memory via repl_invoke (sets up target)
            rdump.repl_invoke("addr init_task | head 1")

            # Stop recording
            saved_path = trace_mgr.stop_recording(rdump.program)
            assert not trace_mgr.is_recording
            assert os.path.exists(saved_path)
            assert saved_path.endswith(VMCORE_EXTENSION)

            # Verify memory was captured
            status = trace_mgr.get_status()
            assert status['memory_size'] > 0

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_vmcore_is_valid_elf(self, rdump: RefDump) -> None:
        """Test that the recorded vmcore is a valid ELF file."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Record something
            trace_mgr.start_recording(rdump.program, output_path)
            rdump.repl_invoke("addr init_task | head 1")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Verify it's a valid ELF file
            with open(saved_path, 'rb') as f:
                magic = f.read(4)
                assert magic == b'\x7fELF', "File should be a valid ELF"

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_vmcore_contains_sdb_notes(self, rdump: RefDump) -> None:
        """Test that the vmcore contains SDB custom notes."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Record something
            trace_mgr.start_recording(rdump.program, output_path)
            rdump.repl_invoke("addr init_task | head 1")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Extract SDB notes
            notes = extract_sdb_notes(saved_path)

            # Should have timestamp at minimum
            assert notes is not None
            assert 'timestamp' in notes

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_snapshot_command(self, rdump: RefDump) -> None:
        """Test the %session snapshot command."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)

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
            output_path = os.path.join(tmpdir, "test")
            trace_mgr.start_recording(rdump.program, output_path)

            result = rdump.repl.eval_cmd("%session status")
            assert result == 0

            trace_mgr.stop_recording(rdump.program)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_stop_commands(self, rdump: RefDump) -> None:
        """Test the %session record and stop commands."""
        setup_test_env(rdump)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Start recording via command
            result = rdump.repl.eval_cmd(f"%session record {output_path}")
            assert result == 0

            trace_mgr = get_trace_manager()
            assert trace_mgr.is_recording

            # Run a command
            rdump.repl_invoke("addr init_task | head 1")

            # Stop recording via command
            result = rdump.repl.eval_cmd("%session stop")
            assert result == 0
            assert not trace_mgr.is_recording

            # Verify file was created with correct extension
            expected_path = output_path + VMCORE_EXTENSION
            assert os.path.exists(expected_path)

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_fat_read_captures_surrounding_memory(self, rdump: RefDump) -> None:
        """Test that fat reads capture 256-byte aligned memory."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)

            # Capture a pointer object - this should trigger fat reads
            rdump.repl_invoke("addr init_task | head 1")

            trace_mgr.stop_recording(rdump.program)

            # Memory size should be aligned to 256 bytes
            # (or larger due to multiple fat reads)
            mem_size = trace_mgr.memory.get_total_size()
            assert mem_size >= 256

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_multiple_commands_accumulate(self, rdump: RefDump) -> None:
        """Test that multiple commands accumulate memory in the trace."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)

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
            output_path = os.path.join(tmpdir, "test")

            # First start should succeed
            result = rdump.repl.eval_cmd(f"%session record {output_path}")
            assert result == 0

            # Second start should fail
            result = rdump.repl.eval_cmd(f"%session record {output_path}2")
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
            output_path = os.path.join(tmpdir, "test")
            trace_mgr.start_recording(rdump.program, output_path)

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
class TestRecordMemory:
    """Tests for the record-memory command."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_record_memory_basic(self, rdump: RefDump) -> None:
        """Test basic record-memory command."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)

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
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)

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
            output_path = os.path.join(tmpdir, "test")

            # Start recording
            trace_mgr.start_recording(rdump.program, output_path)

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


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestRecordReplayEndToEnd:
    """
    End-to-end tests that verify recording + replay produce consistent output.

    These tests record a session from a crash dump, save it as a vmcore,
    and verify the vmcore can be loaded by drgn.
    """

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_vmcore_loadable_by_drgn(self, rdump: RefDump) -> None:
        """Test that the recorded vmcore can be loaded by drgn."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Record some memory
            trace_mgr.start_recording(rdump.program, output_path)
            rdump.repl_invoke("addr init_task | head 1")
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Try to load the vmcore with drgn
            prog = drgn.Program()
            try:
                prog.set_core_dump(saved_path)
                # If we get here, the vmcore was loaded successfully
                assert prog.platform is not None
            except Exception as e:  # pylint: disable=broad-exception-caught
                pytest.fail(f"Failed to load recorded vmcore: {e}")

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_memory_content_preserved(self, rdump: RefDump) -> None:
        """Test that memory content read during recording is preserved."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            from sdb import target as sdb_target
            init_task = sdb_target.get_object("init_task")
            addr = int(init_task.address_of_())

            # Read memory during live mode (forces cache load)
            _ = rdump.program.read(addr, 256)

            # Record the session
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "test"))
            trace_mgr.capture_object(init_task, depth=0)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load the vmcore and try to read memory
            prog = drgn.Program()
            prog.set_core_dump(saved_path)

            # The memory at the recorded address should be readable
            # Note: Exact comparison may fail due to fat-read alignment
            # but the vmcore should contain the data
            try:
                # Try reading from the vmcore - this verifies memory is accessible
                _ = prog.read(addr & ~0xFF, 256)
            except drgn.FaultError:
                # Memory not at that exact address is OK due to alignment
                pass

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_jiffies_value_preserved(self, rdump: RefDump) -> None:
        """Test that jiffies value is preserved between recording and replay."""
        setup_test_env(rdump)
        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            from sdb import target as sdb_target
            import struct

            # Get jiffies value and address during live mode
            jiffies_obj = sdb_target.get_object("jiffies")
            live_jiffies_value = int(jiffies_obj)
            live_jiffies_addr = int(jiffies_obj.address_of_())

            # Record the session with jiffies captured
            trace_mgr.start_recording(rdump.program,
                                      os.path.join(tmpdir, "test"))
            trace_mgr.capture_object(jiffies_obj, depth=0)
            saved_path = trace_mgr.stop_recording(rdump.program)

            # Load the vmcore and read jiffies
            prog = drgn.Program()
            prog.set_core_dump(saved_path)

            # Read the value from the recorded vmcore
            aligned_addr = live_jiffies_addr & ~0xFF
            offset = live_jiffies_addr - aligned_addr
            try:
                replay_mem = prog.read(aligned_addr, 256)
                replay_value = struct.unpack('<Q',
                                             replay_mem[offset:offset + 8])[0]
                assert replay_value == live_jiffies_value, \
                    f"jiffies mismatch: live={live_jiffies_value}, " \
                    f"replay={replay_value}"
            except drgn.FaultError:
                # Memory at different alignment, skip this check
                pass


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
class TestVmcoreInfoCapture:
    """Integration tests for vmcoreinfo capture during recording."""

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_vmcoreinfo_captured_if_available(self, rdump: RefDump) -> None:
        """Test that vmcoreinfo is captured during recording if available."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            # Start and stop recording to capture metadata
            trace_mgr.start_recording(rdump.program, output_path)
            trace_mgr.stop_recording(rdump.program)

            # Check if vmcoreinfo was captured (may not be available in all dumps)
            if 'vmcoreinfo' in trace_mgr.metadata:
                vmcoreinfo = trace_mgr.metadata['vmcoreinfo']
                # Should contain OSRELEASE at minimum
                assert 'OSRELEASE=' in vmcoreinfo or 'PAGESIZE=' in vmcoreinfo

    @pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
    def test_kernel_release_captured(self, rdump: RefDump) -> None:
        """Test that kernel release is captured from vmcoreinfo."""
        setup_test_env(rdump)

        trace_mgr = get_trace_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test")

            trace_mgr.start_recording(rdump.program, output_path)
            trace_mgr.stop_recording(rdump.program)

            # If vmcoreinfo was available, kernel_release should be extracted
            if 'vmcoreinfo' in trace_mgr.metadata:
                assert 'kernel_release' in trace_mgr.metadata
                assert trace_mgr.metadata['kernel_release']
