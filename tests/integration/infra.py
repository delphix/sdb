#
# Copyright 2019, 2023 Delphix
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

# pylint: disable=missing-module-docstring

import glob
import os
import re
import shutil

from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import drgn
import sdb
from sdb.internal.cli import load_debug_info
from sdb.internal.repl import REPL

THIS_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = f"{THIS_DIR}/data"
DUMPS_DIR = f"{DATA_DIR}/dumps"
TEST_OUTPUT_DIR = f"{DATA_DIR}/regression_output"

# OS Crash Dump Related Path/Prefixes
CRASH_PREFIX = f"{DUMPS_DIR}/dump.*"
MODS_DIR = "usr"
ALTERNATIVE_MODS_DIR = "mods"
VMLINUX_PREFIX = "vmlinux-*"

# Userland Core Dump
UCORE_PREFIX = f"{DUMPS_DIR}/archive-core.*"
LIBS_PATH = "lib"
LIBS64_PATH = "lib64"
LIBS_DEBUG_PATH = "usr"
EXEC_DIR = "bin"
ALTERNATIVE_EXEC_DIR = "sbin"
EXPORT_DIR = "export"


def get_all_dump_dir_paths() -> List[str]:
    """
    Returns all the discovered dump directories under the data/dumps folder.
    """
    return get_crash_dump_dir_paths() + get_core_dump_dir_paths()


def get_crash_dump_dir_paths() -> List[str]:
    """
    Get crash dump directory paths as a list of strings if any exists.

    Note: Besides returning the discovered paths, this function is also used as
    a predicate by specific test modules from the test suite to see if they
    should be ran.
    """
    return glob.glob(CRASH_PREFIX)


def get_vmlinux_path(dump_dir_path: str) -> str:
    """
    Get vmlinux path as a string.
    """
    paths = glob.glob(f"{dump_dir_path}/{VMLINUX_PREFIX}")
    assert len(paths) == 1
    return paths[0]


def get_modules_dir(dump_dir_path: str) -> str:
    """
    Get modules directory path as a string.
    """
    paths = glob.glob(f"{dump_dir_path}/{MODS_DIR}")
    if len(paths) == 1:
        return paths[0]
    assert len(paths) == 0

    paths = glob.glob(f"{dump_dir_path}/{ALTERNATIVE_MODS_DIR}")
    assert len(paths) == 1
    return paths[0]


def get_core_dump_dir_paths() -> List[str]:
    """
    Get core dump directory paths as list of strings if any exists.

    Note: Besides returning the discovered path, this function is also used as
    a predicate by specific test modules from the test suite to see if they
    should be ran.
    """
    return glob.glob(UCORE_PREFIX)


def get_libs_path(dump_dir_path: str) -> Optional[str]:
    """
    Get libraries path as string if it exists. None otherwise.
    """
    paths = glob.glob(f"{dump_dir_path}/{LIBS_PATH}")
    assert len(paths) < 2
    if len(paths) == 0:
        return None
    return paths[0]


def get_libs64_path(dump_dir_path: str) -> Optional[str]:
    """
    Get 64-bit libraries path as string if it exists. None otherwise.
    """
    paths = glob.glob(f"{dump_dir_path}/{LIBS64_PATH}")
    assert len(paths) < 2
    if len(paths) == 0:
        return None
    return paths[0]


def get_lib_debug_info_path(dump_dir_path: str) -> Optional[str]:
    """
    Get /usr path with debug libraries as string if it exists. None otherwise.
    """
    paths = glob.glob(f"{dump_dir_path}/{LIBS_DEBUG_PATH}")
    assert len(paths) < 2
    if len(paths) == 0:
        return None
    return paths[0]


def get_export_dir(dump_dir_path: str) -> Optional[str]:
    """
    Get /export path as string if it exists. None otherwise.

    NOTE: This is more delphix-specific and it's there for anything that's
    compiled and ran out of the home directory.
    """
    paths = glob.glob(f"{dump_dir_path}/{EXPORT_DIR}")
    assert len(paths) < 2
    if len(paths) == 0:
        return None
    return paths[0]


def get_binary_dir(dump_dir_path: str) -> Optional[str]:
    """
    Get executable binary directory path as string if it exists.
    None otherwise.
    """
    paths = glob.glob(f"{dump_dir_path}/{EXEC_DIR}")
    if len(paths) == 1:
        return paths[0]
    assert len(paths) == 0

    paths = glob.glob(f"{dump_dir_path}/{ALTERNATIVE_EXEC_DIR}")
    assert len(paths) < 2
    if len(paths) == 0:
        return None
    return paths[0]


def setup_crash_dump_target(dump_dir_path: str, dump_path: str) -> drgn.Program:
    """
    Create a drgn.Program instance and setup the SDB context for all the
    integration tests from the given crash dump path.
    """
    prog = drgn.Program()
    prog.set_core_dump(dump_path)
    load_debug_info(
        prog, [get_vmlinux_path(dump_dir_path),
               get_modules_dir(dump_dir_path)], True, False)
    return prog


def setup_userland_core_target(dump_dir_path: str,
                               dump_path: str) -> drgn.Program:
    """
    Create a drgn.Program instance and setup the SDB context for all the
    integration tests from the given userland core dump path.
    """
    prog = drgn.Program()
    prog.set_core_dump(dump_path)
    debug_info = (p for p in [
        get_lib_debug_info_path(dump_dir_path),
        get_binary_dir(dump_dir_path),
        get_export_dir(dump_dir_path),
        get_libs_path(dump_dir_path),
        get_libs64_path(dump_dir_path)
    ] if p is not None)
    load_debug_info(prog, list(debug_info), True, True)
    return prog


def removeprefix(text: str, prefix: str) -> str:
    """
    NOTE: Until we no longer support Python 3.8 and older we'll use this.
    """
    return text[text.startswith(prefix) and len(prefix):]


class RefDump:
    """
    Represents a reference dump for which the test suite can run commands and
    verify their output and exit code.
    """

    program: drgn.Program
    repl: REPL
    dump_name: str

    def __init__(self, dump_dir_path: str,
                 setup_func: Callable[[str, str], drgn.Program]) -> None:
        """
        NOTE: This object assumes that the folder containg the reference dump has
        the exact same name as the dump file itself.
        """
        self.dump_dir_path = dump_dir_path
        # pylint: disable=comparison-with-callable
        if setup_func == setup_userland_core_target:
            self.dump_name = removeprefix(os.path.basename(dump_dir_path),
                                          "archive-")
            self.is_userland = True
        else:
            self.dump_name = os.path.basename(dump_dir_path)
            self.is_userland = False
        self.dump_path = f"{self.dump_dir_path}/{self.dump_name}"
        assert os.path.isfile(self.dump_path)
        self.setup_func = setup_func

    def setup_target(self) -> None:
        """
        Initialize all the SDB/Drgn context needed for the tests to use the
        reference dump.
        """
        self.program = self.setup_func(self.dump_dir_path, self.dump_path)
        self.repl = REPL(self.program,
                         list(sdb.get_registered_commands().keys()))

    def repl_invoke(self, cmd: str) -> int:
        """
        Invoke the supplied command from the SDB REPL.  Returns exit code of
        the command evaluation and will print any command results in stdout or
        capsys (e.g. when ran by the test suite).
        """
        assert self.program
        assert self.repl
        sdb.target.set_prog(self.program)
        sdb.register_commands()
        return self.repl.eval_cmd(cmd)

    def get_reference_data(self, modname: str, cmd: str) -> Tuple[str, int]:
        """
        Given a module name and a command, find the output file and return a
        tuple containg the expected output and exit code of the given command
        for the supplied dump.
        """
        contents = Path(f"{TEST_OUTPUT_DIR}/{self.dump_name}/{modname}/{cmd}"
                       ).read_text(encoding='utf-8').splitlines(True)
        return ("".join(contents[:-2]), int(contents[-1].strip()))

    def verify_cmd_output_and_code(self,
                                   capsys: Any,
                                   mod: str,
                                   cmd: str,
                                   stripped: bool = False) -> None:
        """
        Run supplied command and verify that its exit code and output match our
        reference results.
        """
        ref_output, ref_code = self.get_reference_data(mod, cmd)

        assert self.repl_invoke(cmd) == ref_code
        captured = capsys.readouterr()
        if not stripped:
            assert captured.out == ref_output
        else:
            for i, n in enumerate(captured.out):
                assert n.strip() == ref_output[i].strip()
            assert len(captured.out) == len(ref_output)

    def generate_output_for_commands(self, cmds: List[str],
                                     dirpath: str) -> None:
        """
        Takes a list of SDB commands in string form, invokes them in the
        context of the current sdb.REPL, and stores their output in the
        directory specified, each under a different file.

        Note: Keep in mind that if the directory specified exists then
        it will be removed together with all of its contents.
        """
        if os.path.exists(dirpath):
            shutil.rmtree(dirpath)
        os.makedirs(dirpath)
        for cmd in cmds:
            with open(f"{dirpath}/{cmd}", 'w', encoding="utf-8") as f:
                with redirect_stdout(f):
                    #
                    # All `print()` output in this block ends up in the file that
                    # we are writing due to `redirect_stdout()`. This includes
                    # whatever output is printed by `repl_invoke()`.
                    #
                    exit_code = self.repl_invoke(cmd)
                    print("@#$ EXIT CODE $#@")
                    print(f"{exit_code}")

    def generate_output_for_test_module(self, modname: str) -> None:
        """
        Generates the regression output for all the commands of a test module
        given  module name. The assumption for this to work automatically is
        that for the given modname "mod" there exist a test module under
        test.integration named test_mod_generic which has a list of commands in
        string form called CMD_TABLE.
        """
        test_mod = import_module(f"tests.integration.test_{modname}_generic")
        self.generate_output_for_commands(
            test_mod.CMD_TABLE,  # type: ignore[attr-defined]
            f"{TEST_OUTPUT_DIR}/{self.dump_name}/{modname}")
        print(
            f"Generated regression test output for {self.dump_name}/{modname}..."
        )

    @staticmethod
    def get_all_generic_test_modules() -> List[str]:
        """
        Look at this current directory and capture all modules with generic
        capsys tests whose filename follows the 'test_{module name}_generic.py'
        convention.
        """
        modnames = []
        for filename in os.listdir(THIS_DIR):
            m = re.search('test_(.+?)_generic.py', filename)
            if m:
                modnames.append(m.group(1))
        return modnames

    def generate_known_regression_output(self) -> None:
        """
        Iterate through all the test modules and generate reference output for
        future regression test runs.
        """
        for modname in self.get_all_generic_test_modules():
            if self.is_userland and modname.startswith("user_"):
                self.generate_output_for_test_module(modname)
            elif not self.is_userland and not modname.startswith("user_"):
                self.generate_output_for_test_module(modname)


def get_all_reference_crash_dumps() -> List[RefDump]:
    """
    Returns all discoverable kernel crash dumps as RefDump objects.
    """
    rdumps = []
    for dump_dir_path in get_crash_dump_dir_paths():
        rdump = RefDump(dump_dir_path, setup_crash_dump_target)
        rdump.setup_target()
        rdumps.append(rdump)
    return rdumps


def get_all_reference_core_dumps() -> List[RefDump]:
    """
    Returns all discoverable userland core dumps as RefDump objects.
    """
    rdumps = []
    for dump_dir_path in get_core_dump_dir_paths():
        rdump = RefDump(dump_dir_path, setup_userland_core_target)
        rdump.setup_target()
        rdumps.append(rdump)
    return rdumps


def get_all_reference_dumps() -> List[RefDump]:
    """
    Returns all discoverable RefDump objects (both kernel and userland dumps).
    """
    return get_all_reference_crash_dumps() + get_all_reference_core_dumps()


def generate_regression_output() -> None:
    """
    Auto-generate the baseline regression output for all the detected test
    modules in this directory.
    """
    for rdump in get_all_reference_dumps():
        rdump.generate_known_regression_output()
