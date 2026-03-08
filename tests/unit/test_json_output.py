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
Tests for the --list-commands and --json CLI flags.
"""

import json
from typing import Any, Dict, List

import pytest
import drgn
import sdb

from tests.unit import MOCK_PROGRAM
from sdb.internal.repl import REPL

# ---------------------------------------------------------------------------
# --list-commands tests
# ---------------------------------------------------------------------------


class TestListCommands:
    """Tests for the _list_commands_json / --list-commands functionality."""

    @staticmethod
    def _get_list_commands_output(
            capsys: pytest.CaptureFixture[str]) -> List[Dict[str, Any]]:
        """Run _list_commands_json and return parsed JSON."""
        import argparse
        from sdb.internal.cli import _list_commands_json
        args = argparse.Namespace(load_commands=[])
        _list_commands_json(args)
        captured = capsys.readouterr()
        result: List[Dict[str, Any]] = json.loads(captured.out)
        return result

    def test_returns_valid_json(self,
                                capsys: pytest.CaptureFixture[str]) -> None:
        result = self._get_list_commands_output(capsys)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_entry_has_required_fields(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        result = self._get_list_commands_output(capsys)
        for entry in result:
            assert "names" in entry
            assert "type" in entry
            assert "summary" in entry
            assert isinstance(entry["names"], list)
            assert len(entry["names"]) >= 1

    def test_known_commands_present(self,
                                    capsys: pytest.CaptureFixture[str]) -> None:
        """Core commands like echo, cast, address should always be present."""
        result = self._get_list_commands_output(capsys)
        all_names: set[str] = set()
        for entry in result:
            all_names.update(entry["names"])

        for expected in ["echo", "cast", "address", "addr", "walk", "help"]:
            assert expected in all_names, f"Expected command '{expected}' not found"

    def test_type_classification(self,
                                 capsys: pytest.CaptureFixture[str]) -> None:
        result = self._get_list_commands_output(capsys)
        by_name: Dict[str, Dict[str, Any]] = {}
        for entry in result:
            for name in entry["names"]:
                by_name[name] = entry

        # 'cast' is a plain Command
        assert by_name["cast"]["type"] == "Command"

        # 'walk' is a Command (the Walk dispatcher, not a Walker itself)
        assert by_name["walk"]["type"] == "Command"

    def test_no_duplicate_entries(self,
                                  capsys: pytest.CaptureFixture[str]) -> None:
        result = self._get_list_commands_output(capsys)
        # Each entry should represent a unique class. Some commands have
        # kernel and userland variants with the same names but different
        # load_on runtimes. We check that (names, load_on) pairs are unique.
        keys = [(tuple(e["names"]), tuple(e.get("load_on", []))) for e in result
               ]
        assert len(keys) == len(set(keys))

    def test_load_on_present(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = self._get_list_commands_output(capsys)
        for entry in result:
            if "load_on" in entry:
                for rt in entry["load_on"]:
                    assert rt in ("All", "Kernel", "Userland", "Module",
                                  "Library")

    def test_sorted_by_first_name(self,
                                  capsys: pytest.CaptureFixture[str]) -> None:
        result = self._get_list_commands_output(capsys)
        first_names = [e["names"][0] for e in result]
        assert first_names == sorted(first_names)


# ---------------------------------------------------------------------------
# _obj_to_json tests
# ---------------------------------------------------------------------------


class TestObjToJson:  # pylint: disable=protected-access
    """Tests for REPL._obj_to_json serialization."""

    def test_void_pointer(self) -> None:
        obj = drgn.Object(MOCK_PROGRAM, 'void *', value=0xdeadbeef)
        result = REPL._obj_to_json(obj)
        assert result["type"] == "void *"
        assert result["value"] == 0xdeadbeef

    def test_int_object(self) -> None:
        obj = drgn.Object(MOCK_PROGRAM, 'int', value=42)
        result = REPL._obj_to_json(obj)
        assert result["type"] == "int"
        assert result["value"] == 42

    def test_negative_int(self) -> None:
        obj = drgn.Object(MOCK_PROGRAM, 'int', value=-1)
        result = REPL._obj_to_json(obj)
        assert result["value"] == -1

    def test_address_present_when_available(self) -> None:
        """Objects backed by memory should have an address field."""
        # Use global_int which is mapped in the mock program at 0xffffffffc0000000
        obj = drgn.Object(MOCK_PROGRAM, 'int', address=0xffffffffc0000000)
        result = REPL._obj_to_json(obj)
        assert "address" in result
        assert result["address"] == hex(0xffffffffc0000000)
        assert result["value"] == 0x01020304

    def test_address_absent_for_value_objects(self) -> None:
        """Objects created with value= (not backed by memory) should not
        have an address field."""
        obj = drgn.Object(MOCK_PROGRAM, 'int', value=1)
        result = REPL._obj_to_json(obj)
        assert "address" not in result

    def test_output_is_json_serializable(self) -> None:
        """Every return value must survive json.dumps without error."""
        obj = drgn.Object(MOCK_PROGRAM, 'void *', value=0)
        result = REPL._obj_to_json(obj)
        serialized = json.dumps(result)
        assert isinstance(serialized, str)

    def test_multiple_objects_array(self) -> None:
        """Simulates what --json would produce: a list of serialized objs."""
        objs = [
            drgn.Object(MOCK_PROGRAM, 'void *', value=0x1),
            drgn.Object(MOCK_PROGRAM, 'int', value=99),
        ]
        results = [REPL._obj_to_json(o) for o in objs]
        assert len(results) == 2
        serialized = json.dumps(results)
        parsed = json.loads(serialized)
        assert parsed[0]["value"] == 1
        assert parsed[1]["value"] == 99


# ---------------------------------------------------------------------------
# REPL JSON mode end-to-end (with MOCK_PROGRAM)
# ---------------------------------------------------------------------------


class TestReplJsonMode:
    """Tests for REPL.eval_cmd with json_mode=True."""

    @staticmethod
    def _make_repl(json_mode: bool = False) -> REPL:
        sdb.target.set_prog(MOCK_PROGRAM)
        sdb.register_commands()
        return REPL(MOCK_PROGRAM,
                    list(sdb.get_registered_commands().keys()),
                    json_mode=json_mode)

    def test_json_mode_echo(self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl(json_mode=True)
        exit_code = repl.eval_cmd("echo 0x1 0x2")
        captured = capsys.readouterr()
        assert exit_code == 0
        result = json.loads(captured.out)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["value"] == 1
        assert result[1]["value"] == 2

    def test_json_mode_empty_output(self,
                                    capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl(json_mode=True)
        exit_code = repl.eval_cmd("echo")
        captured = capsys.readouterr()
        assert exit_code == 0
        result = json.loads(captured.out)
        assert result == []

    def test_json_mode_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = self._make_repl(json_mode=True)
        exit_code = repl.eval_cmd("echo bogus_not_a_number")
        captured = capsys.readouterr()
        assert exit_code == 1
        result = json.loads(captured.out)
        assert "error" in result

    def test_json_mode_pipeline(self,
                                capsys: pytest.CaptureFixture[str]) -> None:
        """echo 0x1 | echo should pass through and produce JSON."""
        repl = self._make_repl(json_mode=True)
        exit_code = repl.eval_cmd("echo 0x1 | echo")
        captured = capsys.readouterr()
        assert exit_code == 0
        result = json.loads(captured.out)
        assert len(result) == 1
        assert result[0]["type"] == "void *"

    def test_non_json_mode_no_json(self,
                                   capsys: pytest.CaptureFixture[str]) -> None:
        """Normal mode should NOT produce JSON output."""
        repl = self._make_repl(json_mode=False)
        exit_code = repl.eval_cmd("echo 0x1")
        captured = capsys.readouterr()
        assert exit_code == 0
        # Should not be valid JSON array
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.out)

    def test_json_mode_command_not_found(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unknown command should produce JSON error."""
        repl = self._make_repl(json_mode=True)
        exit_code = repl.eval_cmd("nonexistent_command_xyz")
        captured = capsys.readouterr()
        assert exit_code == 1
        result = json.loads(captured.out)
        assert "error" in result

    def test_json_mode_resets_flag(self,
                                   capsys: pytest.CaptureFixture[str]) -> None:
        """set_json_mode(False) is called even after errors."""
        repl = self._make_repl(json_mode=True)
        repl.eval_cmd("nonexistent_command_xyz")
        _ = capsys.readouterr()
        # After eval_cmd returns, the global flag should be reset
        from sdb import command as cmd_mod
        assert not cmd_mod._json_mode  # pylint: disable=protected-access
