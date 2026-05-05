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
Unit tests for the external command loader (sdb.loader) and
the library API entry point (sdb.start).
"""

import os
import shutil
import sys
import tempfile
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from sdb.command import all_commands
from sdb.loader import load_external_commands, _import_file  # pylint: disable=protected-access

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SAMPLE_COMMANDS_DIR = os.path.join(DATA_DIR, "sample_commands")
SAMPLE_COMMANDS_SUBDIR = os.path.join(DATA_DIR, "sample_commands_subdir")
HELLO_FILE = os.path.join(SAMPLE_COMMANDS_DIR, "hello.py")


def _command_names() -> List[str]:
    """Return sorted list of all known command names."""
    return sorted(n for cls in all_commands for n in cls.names)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_ext_modules() -> Any:
    """Remove any sdb_ext.* modules after each test so they can be reimported."""
    yield
    to_remove = [k for k in sys.modules if k.startswith("sdb_ext.")]
    for k in to_remove:
        del sys.modules[k]


# ---------------------------------------------------------------------------
# load_external_commands -- single file
# ---------------------------------------------------------------------------


class TestLoadSingleFile:

    def test_load_single_file(self) -> None:
        new_names = load_external_commands(HELLO_FILE)
        assert "hello_ext" in new_names

    def test_load_single_file_names_in_all_commands(self) -> None:
        load_external_commands(HELLO_FILE)
        assert "hello_ext" in _command_names()

    def test_load_same_file_twice_is_idempotent(self) -> None:
        """Loading the same path twice still registers the command."""
        first = load_external_commands(HELLO_FILE)
        assert "hello_ext" in first
        second = load_external_commands(HELLO_FILE)
        assert "hello_ext" in second


# ---------------------------------------------------------------------------
# load_external_commands -- directory
# ---------------------------------------------------------------------------


class TestLoadDirectory:

    def test_load_flat_directory(self) -> None:
        new_names = load_external_commands(SAMPLE_COMMANDS_DIR)
        assert "hello_ext" in new_names
        assert "greet_ext" in new_names
        assert "kernel_only_ext" in new_names

    def test_load_nested_directory(self) -> None:
        new_names = load_external_commands(SAMPLE_COMMANDS_SUBDIR)
        assert "top_level_ext" in new_names
        assert "nested_ext" in new_names

    def test_skips_dunder_files(self) -> None:
        """__init__.py and __pycache__ files should be skipped."""
        tmpdir = tempfile.mkdtemp()
        try:
            init_path = os.path.join(tmpdir, "__init__.py")
            with open(init_path, "w", encoding="utf-8") as f:
                f.write("# should be skipped\n")
            cmd_path = os.path.join(tmpdir, "real_cmd.py")
            with open(cmd_path, "w", encoding="utf-8") as f:
                f.write("import sdb\n"
                        "class SkipTest(sdb.Command):\n"
                        "    names = ['skip_test_ext']\n"
                        "    load_on = [sdb.All()]\n"
                        "    def _call(self, objs):\n"
                        "        yield from objs\n")
            new_names = load_external_commands(tmpdir)
            assert "skip_test_ext" in new_names
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# load_external_commands -- error handling
# ---------------------------------------------------------------------------


class TestLoadErrors:

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            load_external_commands("/no/such/path/commands")

    def test_non_py_file_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt",
                                         delete=False) as tmpfile:
            tmpfile_name = tmpfile.name
        try:
            with pytest.raises(ValueError, match="must be a .py file"):
                load_external_commands(tmpfile_name)
        finally:
            os.unlink(tmpfile_name)

    def test_bad_syntax_raises(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            bad_file = os.path.join(tmpdir, "bad.py")
            with open(bad_file, "w", encoding="utf-8") as f:
                f.write("this is not valid python !!!\n")
            with pytest.raises(SyntaxError):
                load_external_commands(bad_file)
        finally:
            shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# _import_file -- low-level
# ---------------------------------------------------------------------------


class TestImportFile:

    def test_import_file_adds_to_sys_modules(self) -> None:
        _import_file(HELLO_FILE)
        matching = [k for k in sys.modules if k.startswith("sdb_ext.hello")]
        assert len(matching) >= 1

    def test_import_file_deduplication(self) -> None:
        """Importing the same file twice gets unique module names."""
        _import_file(HELLO_FILE)
        _import_file(HELLO_FILE)
        matching = [k for k in sys.modules if k.startswith("sdb_ext.hello")]
        assert len(matching) >= 2


# ---------------------------------------------------------------------------
# SDB_COMMANDS_PATH environment variable
# ---------------------------------------------------------------------------


class TestEnvVar:  # pylint: disable=too-few-public-methods

    def test_env_var_loads_commands(self) -> None:
        """sdb.start() should honour SDB_COMMANDS_PATH."""
        import sdb

        mock_prog = MagicMock()
        mock_prog.flags = 0
        mock_prog.threads.return_value = iter([])
        mock_prog.crashed_thread.side_effect = ValueError

        with patch.dict(os.environ, {"SDB_COMMANDS_PATH": SAMPLE_COMMANDS_DIR}):
            with patch.object(sdb, "register_commands"):
                with patch("sdb.internal.repl.REPL") as mock_repl_cls:
                    mock_repl = MagicMock()
                    mock_repl_cls.return_value = mock_repl
                    with patch("sdb.target.set_prog"):
                        with patch("sdb.target.set_thread"):
                            with patch("sdb.target.set_frame"):
                                try:
                                    sdb.start(mock_prog, eval_cmd="echo 0x0")
                                except SystemExit:
                                    pass

        assert "hello_ext" in _command_names()


# ---------------------------------------------------------------------------
# CLI --load-commands
# ---------------------------------------------------------------------------


class TestCLILoadCommands:

    def test_load_external_command_paths(self) -> None:
        """_load_external_command_paths should process args.load_commands."""
        import argparse
        from sdb.internal.cli import _load_external_command_paths

        args = argparse.Namespace(load_commands=[SAMPLE_COMMANDS_DIR])
        with patch.dict(os.environ, {}, clear=True):
            _load_external_command_paths(args, quiet=True)

        assert "hello_ext" in _command_names()
        assert "greet_ext" in _command_names()

    def test_load_external_command_paths_with_env(self) -> None:
        """SDB_COMMANDS_PATH should also be honoured by the CLI helper."""
        import argparse
        from sdb.internal.cli import _load_external_command_paths

        args = argparse.Namespace(load_commands=[])
        with patch.dict(os.environ,
                        {"SDB_COMMANDS_PATH": SAMPLE_COMMANDS_SUBDIR}):
            _load_external_command_paths(args, quiet=True)

        assert "top_level_ext" in _command_names()
        assert "nested_ext" in _command_names()

    def test_bad_path_prints_warning(self, capsys: Any) -> None:
        """A missing path should produce a warning, not crash."""
        import argparse
        from sdb.internal.cli import _load_external_command_paths

        args = argparse.Namespace(load_commands=["/no/such/dir"])
        with patch.dict(os.environ, {}, clear=True):
            _load_external_command_paths(args, quiet=False)

        captured = capsys.readouterr()
        assert "does not exist" in captured.err


# ---------------------------------------------------------------------------
# REPL %load-commands meta-command
# ---------------------------------------------------------------------------


class TestREPLLoadCommands:

    def _make_repl(self) -> Any:
        from sdb.internal.repl import REPL
        mock_prog = MagicMock(spec_set=["flags", "platform"])
        mock_prog.flags = 0
        mock_prog.platform = "test"
        return REPL(mock_prog, ["echo", "help"])

    def test_load_commands_success(self) -> None:
        repl = self._make_repl()
        result = repl.eval_session_cmd(f"load-commands {SAMPLE_COMMANDS_DIR}")
        assert result == 0

    def test_load_commands_no_args(self, capsys: Any) -> None:
        repl = self._make_repl()
        result = repl.eval_session_cmd("load-commands")
        assert result == 2
        assert "Usage" in capsys.readouterr().out

    def test_load_commands_bad_path(self, capsys: Any) -> None:
        repl = self._make_repl()
        result = repl.eval_session_cmd("load-commands /no/such/path")
        assert result == 1
        assert "Error" in capsys.readouterr().out

    def test_load_commands_refreshes_vocabulary(self) -> None:
        repl = self._make_repl()
        old_vocab = list(repl.vocabulary)
        repl.eval_session_cmd(f"load-commands {SAMPLE_COMMANDS_DIR}")
        assert len(repl.vocabulary) > len(old_vocab)

    def test_unknown_meta_command(self, capsys: Any) -> None:
        repl = self._make_repl()
        result = repl.eval_session_cmd("bogus-thing")
        assert result == 1
        assert "%load-commands" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# REPL pre_cmd_hook
# ---------------------------------------------------------------------------


class TestPreCmdHook:

    def test_hook_called_on_eval(self) -> None:
        from sdb.internal.repl import REPL
        hook = MagicMock()
        mock_prog = MagicMock(spec_set=["flags", "platform"])
        mock_prog.flags = 0
        mock_prog.platform = "test"
        repl = REPL(mock_prog, ["echo"], pre_cmd_hook=hook)

        with patch("sdb.internal.repl.invoke", return_value=iter([])):
            with patch("sdb.internal.repl.get_trace_manager") as mock_tm:
                mock_tm.return_value.is_recording = False
                repl.eval_cmd("echo 0x0")

        hook.assert_called_once()

    def test_hook_not_called_for_meta_commands(self) -> None:
        from sdb.internal.repl import REPL
        hook = MagicMock()
        mock_prog = MagicMock(spec_set=["flags", "platform"])
        mock_prog.flags = 0
        mock_prog.platform = "test"
        repl = REPL(mock_prog, ["echo"], pre_cmd_hook=hook)

        repl.eval_cmd(f"%load-commands {SAMPLE_COMMANDS_DIR}")

        hook.assert_not_called()


# ---------------------------------------------------------------------------
# Library API -- sdb.start()
# ---------------------------------------------------------------------------


class TestLibraryAPI:

    def test_start_accepts_external_program(self) -> None:
        """sdb.start() should install the provided program and run the REPL."""
        import sdb
        import sdb.target as sdb_target

        mock_prog = MagicMock()
        mock_prog.flags = 0
        mock_prog.threads.return_value = iter([])
        mock_prog.crashed_thread.side_effect = ValueError

        with patch("sdb.internal.repl.REPL") as mock_repl_cls:
            mock_repl = MagicMock()
            mock_repl.eval_cmd.return_value = 0
            mock_repl_cls.return_value = mock_repl
            with patch.object(sdb_target, "set_prog") as mock_set_prog:
                with patch.object(sdb_target, "set_thread"):
                    with patch.object(sdb_target, "set_frame"):
                        with patch.object(sdb, "register_commands"):
                            try:
                                sdb.start(mock_prog, eval_cmd="echo 0x0")
                            except SystemExit:
                                pass

            mock_set_prog.assert_called_once_with(mock_prog)
            mock_repl.eval_cmd.assert_called_once_with("echo 0x0")

    def test_start_loads_command_paths(self) -> None:
        """sdb.start() should load commands from provided paths."""
        import sdb
        import sdb.target as sdb_target

        mock_prog = MagicMock()
        mock_prog.flags = 0
        mock_prog.threads.return_value = iter([])
        mock_prog.crashed_thread.side_effect = ValueError

        with patch("sdb.internal.repl.REPL") as mock_repl_cls:
            mock_repl = MagicMock()
            mock_repl.eval_cmd.return_value = 0
            mock_repl_cls.return_value = mock_repl
            with patch.object(sdb_target, "set_prog"):
                with patch.object(sdb_target, "set_thread"):
                    with patch.object(sdb_target, "set_frame"):
                        with patch.object(sdb, "register_commands"):
                            try:
                                sdb.start(
                                    mock_prog,
                                    command_paths=[SAMPLE_COMMANDS_DIR],
                                    eval_cmd="echo 0x0",
                                )
                            except SystemExit:
                                pass

        assert "hello_ext" in _command_names()
        assert "greet_ext" in _command_names()

    def test_start_passes_prompt(self) -> None:
        """sdb.start() should forward the prompt to the REPL."""
        import sdb
        import sdb.target as sdb_target

        mock_prog = MagicMock()
        mock_prog.flags = 0
        mock_prog.threads.return_value = iter([])
        mock_prog.crashed_thread.side_effect = ValueError

        with patch("sdb.internal.repl.REPL") as mock_repl_cls:
            mock_repl = MagicMock()
            mock_repl.eval_cmd.return_value = 0
            mock_repl_cls.return_value = mock_repl
            with patch.object(sdb_target, "set_prog"):
                with patch.object(sdb_target, "set_thread"):
                    with patch.object(sdb_target, "set_frame"):
                        with patch.object(sdb, "register_commands"):
                            try:
                                sdb.start(mock_prog,
                                          prompt="gw> ",
                                          eval_cmd="echo 0x0")
                            except SystemExit:
                                pass

            _, kwargs = mock_repl_cls.call_args
            assert kwargs["prompt"] == "gw> "

    def test_start_passes_pre_cmd_hook(self) -> None:
        """sdb.start() should forward pre_cmd_hook to the REPL."""
        import sdb
        import sdb.target as sdb_target

        mock_prog = MagicMock()
        mock_prog.flags = 0
        mock_prog.threads.return_value = iter([])
        mock_prog.crashed_thread.side_effect = ValueError

        hook = MagicMock()

        with patch("sdb.internal.repl.REPL") as mock_repl_cls:
            mock_repl = MagicMock()
            mock_repl.eval_cmd.return_value = 0
            mock_repl_cls.return_value = mock_repl
            with patch.object(sdb_target, "set_prog"):
                with patch.object(sdb_target, "set_thread"):
                    with patch.object(sdb_target, "set_frame"):
                        with patch.object(sdb, "register_commands"):
                            try:
                                sdb.start(mock_prog,
                                          pre_cmd_hook=hook,
                                          eval_cmd="echo 0x0")
                            except SystemExit:
                                pass

            _, kwargs = mock_repl_cls.call_args
            assert kwargs["pre_cmd_hook"] is hook

    def test_start_interactive_mode(self) -> None:
        """Without eval_cmd, sdb.start() should call start_session()."""
        import sdb
        import sdb.target as sdb_target

        mock_prog = MagicMock()
        mock_prog.flags = 0
        mock_prog.threads.return_value = iter([])
        mock_prog.crashed_thread.side_effect = ValueError

        with patch("sdb.internal.repl.REPL") as mock_repl_cls:
            mock_repl = MagicMock()
            mock_repl_cls.return_value = mock_repl
            with patch.object(sdb_target, "set_prog"):
                with patch.object(sdb_target, "set_thread"):
                    with patch.object(sdb_target, "set_frame"):
                        with patch.object(sdb, "register_commands"):
                            sdb.start(mock_prog)

            mock_repl.start_session.assert_called_once()


# ---------------------------------------------------------------------------
# REPL.refresh_vocabulary
# ---------------------------------------------------------------------------


class TestRefreshVocabulary:  # pylint: disable=too-few-public-methods

    def test_refresh_updates_vocabulary(self) -> None:
        from sdb.internal.repl import REPL
        mock_prog = MagicMock(spec_set=["flags", "platform"])
        mock_prog.flags = 0
        mock_prog.platform = "test"
        repl = REPL(mock_prog, ["old_cmd"])

        assert "old_cmd" in repl.vocabulary

        with patch("sdb.command.get_registered_commands",
                   return_value={
                       "new_a": None,
                       "new_b": None,
                   }):
            repl.refresh_vocabulary()

        assert "new_a" in repl.vocabulary
        assert "new_b" in repl.vocabulary
