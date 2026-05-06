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
Tests for sdb exit code constants and their use in the REPL.
"""

import pytest

import sdb

from tests.unit import MOCK_PROGRAM
from sdb.internal.repl import REPL


class TestExitCodeConstants:
    """Verify the exit code constants are exported and have correct values."""

    def test_exit_success_is_zero(self) -> None:
        assert sdb.EXIT_SUCCESS == 0

    def test_exit_error_is_one(self) -> None:
        assert sdb.EXIT_ERROR == 1

    def test_exit_bad_args_is_two(self) -> None:
        assert sdb.EXIT_BAD_ARGS == 2

    def test_constants_in_all(self) -> None:
        assert 'EXIT_SUCCESS' in sdb.__all__
        assert 'EXIT_ERROR' in sdb.__all__
        assert 'EXIT_BAD_ARGS' in sdb.__all__


class TestReplUsesConstants:  # pylint: disable=unused-argument
    """Verify the REPL returns the named constants, not magic numbers."""

    @staticmethod
    def _make_repl() -> REPL:
        sdb.target.set_prog(MOCK_PROGRAM)
        sdb.register_commands()
        return REPL(MOCK_PROGRAM, list(sdb.get_registered_commands().keys()))

    def test_success_returns_exit_success(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        assert repl.eval_cmd("echo 0x1") == sdb.EXIT_SUCCESS

    def test_command_error_returns_exit_error(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        assert repl.eval_cmd("nonexistent_cmd_xyz") == sdb.EXIT_ERROR

    def test_bad_args_returns_exit_bad_args(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl()
        assert repl.eval_cmd("head -n notanumber") == sdb.EXIT_BAD_ARGS
