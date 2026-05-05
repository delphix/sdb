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
Tests for sdb.open_dump() convenience function.
"""

import pathlib
from unittest import mock

import pytest
import drgn
import sdb


class TestOpenDumpErrors:
    """Test error handling in open_dump()."""

    def test_missing_core_file(self) -> None:
        with pytest.raises(FileNotFoundError, match="core file not found"):
            sdb.open_dump("/nonexistent/vmlinux", "/nonexistent/vmcore")

    def test_missing_object_file(self, tmp_path: pathlib.Path) -> None:
        core = tmp_path / "vmcore"
        core.write_bytes(b"fake")
        with pytest.raises(FileNotFoundError, match="object file not found"):
            sdb.open_dump("/nonexistent/vmlinux", str(core))

    def test_open_dump_in_all(self) -> None:
        assert 'open_dump' in sdb.__all__


class TestOpenDumpHappyPath:
    """Test the happy path using mocks for drgn.Program."""

    @mock.patch('sdb.connect')
    @mock.patch('drgn.Program')
    def test_calls_set_core_dump_and_connect(self,
                                             mock_prog_cls: mock.MagicMock,
                                             mock_connect: mock.MagicMock,
                                             tmp_path: pathlib.Path) -> None:
        # Create fake files
        obj_file = tmp_path / "vmlinux"
        obj_file.write_bytes(b"fake vmlinux")
        core_file = tmp_path / "vmcore"
        core_file.write_bytes(b"fake vmcore")

        mock_prog = mock.MagicMock()
        mock_prog_cls.return_value = mock_prog
        mock_connect.return_value = mock_prog

        result = sdb.open_dump(str(obj_file), str(core_file))

        mock_prog.set_core_dump.assert_called_once_with(str(core_file))
        mock_prog.load_debug_info.assert_called_once_with([str(obj_file)])
        mock_connect.assert_called_once_with(mock_prog, command_paths=None)
        assert result is mock_prog

    @mock.patch('sdb.connect')
    @mock.patch('drgn.Program')
    def test_passes_command_paths(self, mock_prog_cls: mock.MagicMock,
                                  mock_connect: mock.MagicMock,
                                  tmp_path: pathlib.Path) -> None:
        obj_file = tmp_path / "vmlinux"
        obj_file.write_bytes(b"fake")
        core_file = tmp_path / "vmcore"
        core_file.write_bytes(b"fake")

        mock_prog = mock.MagicMock()
        mock_prog_cls.return_value = mock_prog
        mock_connect.return_value = mock_prog

        sdb.open_dump(str(obj_file), str(core_file), command_paths=["/my/cmds"])

        mock_connect.assert_called_once_with(mock_prog,
                                             command_paths=["/my/cmds"])

    @mock.patch('sdb.connect')
    @mock.patch('drgn.Program')
    def test_symbol_search_dirs(self, mock_prog_cls: mock.MagicMock,
                                mock_connect: mock.MagicMock,
                                tmp_path: pathlib.Path) -> None:
        obj_file = tmp_path / "vmlinux"
        obj_file.write_bytes(b"fake")
        core_file = tmp_path / "vmcore"
        core_file.write_bytes(b"fake")

        # Create a symbol search dir with a .ko file
        sym_dir = tmp_path / "symbols"
        sym_dir.mkdir()
        ko_file = sym_dir / "zfs.ko"
        ko_file.write_bytes(b"fake ko")

        mock_prog = mock.MagicMock()
        mock_prog_cls.return_value = mock_prog
        mock_connect.return_value = mock_prog

        sdb.open_dump(str(obj_file),
                      str(core_file),
                      symbol_search=[str(sym_dir)])

        # Should be called twice: once for vmlinux, once for the dir
        assert mock_prog.load_debug_info.call_count == 2

    @mock.patch('sdb.connect')
    @mock.patch('drgn.Program')
    def test_quiet_suppresses_warnings(
            self, mock_prog_cls: mock.MagicMock, mock_connect: mock.MagicMock,
            tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
        obj_file = tmp_path / "vmlinux"
        obj_file.write_bytes(b"fake")
        core_file = tmp_path / "vmcore"
        core_file.write_bytes(b"fake")

        mock_prog = mock.MagicMock()
        mock_prog_cls.return_value = mock_prog
        mock_prog.load_debug_info.side_effect = drgn.MissingDebugInfoError(
            "missing")
        mock_connect.return_value = mock_prog

        sdb.open_dump(str(obj_file), str(core_file), quiet=True)

        captured = capsys.readouterr()
        assert "missing" not in captured.err
