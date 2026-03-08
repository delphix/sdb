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
Tests for sdb.connect() and sdb.run() programmatic API.
"""

import pytest
import drgn
import sdb

from tests.unit import MOCK_PROGRAM

# ---------------------------------------------------------------------------
# sdb.connect() tests
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for sdb.connect()."""

    def test_returns_same_program(self) -> None:
        result = sdb.connect(MOCK_PROGRAM)
        assert result is MOCK_PROGRAM

    def test_sets_prog(self) -> None:
        sdb.connect(MOCK_PROGRAM)
        assert sdb.get_prog() is MOCK_PROGRAM

    def test_registers_commands(self) -> None:
        sdb.connect(MOCK_PROGRAM)
        cmds = sdb.get_registered_commands()
        assert "echo" in cmds
        assert "cast" in cmds
        assert "address" in cmds

    def test_idempotent(self) -> None:
        """Calling connect() multiple times should not cause errors."""
        sdb.connect(MOCK_PROGRAM)
        sdb.connect(MOCK_PROGRAM)
        assert sdb.get_prog() is MOCK_PROGRAM


# ---------------------------------------------------------------------------
# sdb.run() tests
# ---------------------------------------------------------------------------


class TestRun:
    """Tests for sdb.run()."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        sdb.connect(MOCK_PROGRAM)

    def test_returns_list(self) -> None:
        result = sdb.run("echo 0x1")
        assert isinstance(result, list)

    def test_echo_single_value(self) -> None:
        result = sdb.run("echo 0x42")
        assert len(result) == 1
        assert result[0].value_() == 0x42

    def test_echo_multiple_values(self) -> None:
        result = sdb.run("echo 0x1 0x2 0x3")
        assert len(result) == 3
        assert [o.value_() for o in result] == [1, 2, 3]

    def test_pipeline(self) -> None:
        result = sdb.run("echo 0x1 0x2 | echo")
        assert len(result) == 2

    def test_empty_result(self) -> None:
        result = sdb.run("echo")
        assert not result

    def test_with_input_objects(self) -> None:
        input_objs = [drgn.Object(MOCK_PROGRAM, 'void *', value=0xbeef)]
        result = sdb.run("echo", input_objs=input_objs)
        assert len(result) == 1
        assert result[0].value_() == 0xbeef

    def test_cast_pipeline(self) -> None:
        result = sdb.run("echo 0x42 | cast int")
        assert len(result) == 1
        assert result[0].type_.type_name() == "int"

    def test_command_not_found_raises(self) -> None:
        with pytest.raises(sdb.CommandNotFoundError):
            sdb.run("nonexistent_command_xyz")

    def test_command_error_raises(self) -> None:
        with pytest.raises(sdb.CommandInvalidInputError):
            sdb.run("echo bogus_not_a_number")

    def test_count_pipeline(self) -> None:
        result = sdb.run("echo 0x1 0x2 0x3 | count")
        assert len(result) == 1
        assert result[0].value_() == 3

    def test_head_pipeline(self) -> None:
        result = sdb.run("echo 0x1 0x2 0x3 | head 2")
        assert len(result) == 2

    def test_chained_run_calls(self) -> None:
        """Multiple sdb.run() calls should work independently."""
        r1 = sdb.run("echo 0x1")
        r2 = sdb.run("echo 0x2")
        assert r1[0].value_() == 1
        assert r2[0].value_() == 2

    def test_run_with_address_lookup(self) -> None:
        """Test addr command for a known mock symbol."""
        result = sdb.run("addr global_int")
        assert len(result) == 1
        # addr returns a pointer to global_int, not the dereferenced value
        assert result[0].value_() == 0xffffffffc0000000

    def test_run_pipeline_with_member(self) -> None:
        """Test member access on a struct."""
        result = sdb.run("addr global_struct | member ts_int")
        assert len(result) == 1
        assert result[0].value_() == 1
