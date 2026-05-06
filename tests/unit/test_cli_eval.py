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
Tests for multiple -e flags, stdin script mode, and exit code consistency.
"""

import argparse
import io
import sys
from unittest import mock

import pytest

import sdb

from tests.unit import MOCK_PROGRAM
from sdb.internal.cli import _get_eval_commands, _eval_commands
from sdb.internal.repl import REPL

# ---------------------------------------------------------------------------
# _get_eval_commands tests
# ---------------------------------------------------------------------------


class TestGetEvalCommands:
    """Tests for _get_eval_commands helper."""

    def test_no_eval_no_stdin(self) -> None:
        args = argparse.Namespace(eval=[], stdin_script=False)
        assert not _get_eval_commands(args)

    def test_single_eval(self) -> None:
        args = argparse.Namespace(eval=["echo 0x1"], stdin_script=False)
        assert _get_eval_commands(args) == ["echo 0x1"]

    def test_multiple_eval(self) -> None:
        args = argparse.Namespace(
            eval=["echo 0x1", "echo 0x2", "echo 0x3"],
            stdin_script=False,
        )
        assert _get_eval_commands(args) == ["echo 0x1", "echo 0x2", "echo 0x3"]

    def test_stdin_script(self) -> None:
        fake_stdin = io.StringIO("echo 0x1\necho 0x2\n# comment\n\n")
        args = argparse.Namespace(eval=[], stdin_script=True)
        with mock.patch.object(sys, 'stdin', fake_stdin):
            cmds = _get_eval_commands(args)
        assert cmds == ["echo 0x1", "echo 0x2"]

    def test_stdin_script_with_eval(self) -> None:
        """Commands from -e come before stdin commands."""
        fake_stdin = io.StringIO("echo 0x3\n")
        args = argparse.Namespace(
            eval=["echo 0x1", "echo 0x2"],
            stdin_script=True,
        )
        with mock.patch.object(sys, 'stdin', fake_stdin):
            cmds = _get_eval_commands(args)
        assert cmds == ["echo 0x1", "echo 0x2", "echo 0x3"]

    def test_stdin_empty(self) -> None:
        fake_stdin = io.StringIO("")
        args = argparse.Namespace(eval=[], stdin_script=True)
        with mock.patch.object(sys, 'stdin', fake_stdin):
            cmds = _get_eval_commands(args)
        assert not cmds

    def test_stdin_only_comments_and_blanks(self) -> None:
        fake_stdin = io.StringIO("# just a comment\n\n   \n# another\n")
        args = argparse.Namespace(eval=[], stdin_script=True)
        with mock.patch.object(sys, 'stdin', fake_stdin):
            cmds = _get_eval_commands(args)
        assert not cmds


# ---------------------------------------------------------------------------
# _eval_commands tests
# ---------------------------------------------------------------------------


class TestEvalCommands:  # pylint: disable=unused-argument
    """Tests for _eval_commands — sequential multi-command execution."""

    @staticmethod
    def _make_repl(json_mode: bool = False) -> REPL:
        sdb.target.set_prog(MOCK_PROGRAM)
        sdb.register_commands()
        return REPL(MOCK_PROGRAM,
                    list(sdb.get_registered_commands().keys()),
                    json_mode=json_mode)

    def test_all_succeed(self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        exit_code = _eval_commands(repl, ["echo 0x1", "echo 0x2"])
        assert exit_code == 0

    def test_first_fails_stops_early(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        exit_code = _eval_commands(repl, ["echo bogus", "echo 0x1"])
        assert exit_code == 1
        # Second command should not have run, so only the error output
        captured = capsys.readouterr()
        assert "(void *)0x1" not in captured.out

    def test_middle_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        exit_code = _eval_commands(repl,
                                   ["echo 0x1", "nonexistent_cmd", "echo 0x2"])
        assert exit_code == 1

    def test_single_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        exit_code = _eval_commands(repl, ["echo 0x42"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "0x42" in captured.out

    def test_empty_list(self) -> None:
        repl = self._make_repl()
        exit_code = _eval_commands(repl, [])
        assert exit_code == 0

    def test_json_mode_multiple_commands(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        """Each command in JSON mode produces its own JSON array."""
        repl = self._make_repl(json_mode=True)
        exit_code = _eval_commands(repl, ["echo 0x1", "echo 0x2"])
        assert exit_code == 0
        captured = capsys.readouterr()
        # Should have two JSON arrays in the output
        lines = captured.out.strip()
        # Split on the boundary between ] and [
        parts = lines.split("]\n[")
        assert len(parts) == 2


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------


class TestExitCodes:  # pylint: disable=unused-argument
    """Tests verifying exit codes for various command outcomes."""

    @staticmethod
    def _make_repl() -> REPL:
        sdb.target.set_prog(MOCK_PROGRAM)
        sdb.register_commands()
        return REPL(MOCK_PROGRAM, list(sdb.get_registered_commands().keys()))

    def test_success_returns_0(self,
                               capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        assert repl.eval_cmd("echo 0x1") == 0

    def test_command_not_found_returns_1(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        assert repl.eval_cmd("nonexistent_cmd_xyz") == 1

    def test_command_error_returns_1(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        assert repl.eval_cmd("echo bogus") == 1

    def test_bad_args_returns_2(self,
                                capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        # head requires a valid argument
        assert repl.eval_cmd("head -n notanumber") == 2

    def test_empty_command_returns_0(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty pipeline with no output is still success."""
        repl = self._make_repl()
        assert repl.eval_cmd("echo") == 0


# ---------------------------------------------------------------------------
# argparse -e append behavior test
# ---------------------------------------------------------------------------


class TestArgparseMultipleEval:
    """Test that argparse correctly collects multiple -e flags."""

    def test_argparse_collects_multiple_e(self) -> None:
        """Verify -e action='append' collects all values."""
        from sdb.internal.cli import parse_arguments
        with mock.patch('sys.argv', ['sdb', '-e', 'cmd1', '-e', 'cmd2']):
            args = parse_arguments()
        assert args.eval == ['cmd1', 'cmd2']

    def test_argparse_single_e(self) -> None:
        from sdb.internal.cli import parse_arguments
        with mock.patch('sys.argv', ['sdb', '-e', 'cmd1']):
            args = parse_arguments()
        assert args.eval == ['cmd1']

    def test_argparse_no_e(self) -> None:
        from sdb.internal.cli import parse_arguments
        with mock.patch('sys.argv', ['sdb']):
            args = parse_arguments()
        assert args.eval == []
