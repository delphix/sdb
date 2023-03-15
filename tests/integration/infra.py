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
from typing import Iterable, List, Optional

import drgn
import sdb
from sdb.internal.cli import load_debug_info
from sdb.internal.repl import REPL

THIS_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = f"{THIS_DIR}/data"
TEST_OUTPUT_DIR = f"{DATA_DIR}/regression_output"

# OS Crash Dump Related Path/Prefixes
CRASH_PREFIX = f"{DATA_DIR}/dump.*"
MODS_DIR = f"{DATA_DIR}/usr"
ALTERNATIVE_MODS_DIR = f"{DATA_DIR}/mods"
VMLINUX_PREFIX = f"{DATA_DIR}/vmlinux-*"

# Userland Core Dump
UCORE_PREFIX = f"{DATA_DIR}/core.*"
LIBS_PATH = f"{DATA_DIR}/lib"
LIBS64_PATH = f"{DATA_DIR}/lib64"
LIBS_DEBUG_PATH = f"{DATA_DIR}/usr"
EXEC_DIR = f"{DATA_DIR}/bin"
ALTERNATIVE_EXEC_DIR = f"{DATA_DIR}/sbin"


def get_path_from_prefix(prefix: str) -> Optional[str]:
    """
    Helper for finding required files by dump type.
    """
    res = glob.glob(prefix)
    if len(res) == 1:
        return res[0]
    assert len(res) == 0
    return None


def get_crash_dump_path() -> Optional[str]:
    """
    Get crash dump path as string if it exists. None otherwise.

    Note: Besides returning the discovered path, this function is also used as
    a predicate by specific test modules from the test suite to see if they
    should be ran.
    """
    return get_path_from_prefix(CRASH_PREFIX)


def get_vmlinux_path() -> Optional[str]:
    """
    Get vmlinux path as string if it exists. None otherwise.
    """
    return get_path_from_prefix(VMLINUX_PREFIX)


def get_modules_dir() -> Optional[str]:
    """
    Get modules directory path as string if it exists.
    None otherwise.
    """
    path = get_path_from_prefix(MODS_DIR)
    if not path:
        return get_path_from_prefix(ALTERNATIVE_MODS_DIR)
    return path


def get_core_dump_path() -> Optional[str]:
    """
    Get core dump path as string if it exists. None otherwise.

    Note: Besides returning the discovered path, this function is also used as
    a predicate by specific test modules from the test suite to see if they
    should be ran.
    """
    return get_path_from_prefix(UCORE_PREFIX)


def get_libs_path() -> Optional[str]:
    """
    Get libraries path as string if it exists. None otherwise.
    """
    return get_path_from_prefix(LIBS_PATH)


def get_libs64_path() -> Optional[str]:
    """
    Get 64-bit libraries path as string if it exists. None otherwise.
    """
    return get_path_from_prefix(LIBS64_PATH)


def get_lib_debug_info_path() -> Optional[str]:
    """
    Get 64-bit libraries path as string if it exists. None otherwise.
    """
    return get_path_from_prefix(LIBS_DEBUG_PATH)


def get_binary_dir() -> Optional[str]:
    """
    Get executable binary directory path as string if it exists.
    None otherwise.
    """
    path = get_path_from_prefix(EXEC_DIR)
    if not path:
        return get_path_from_prefix(ALTERNATIVE_EXEC_DIR)
    return path


def setup_target() -> Optional[drgn.Program]:
    """
    Create a drgn.Program instance and setup the SDB context for all the
    integration tests. If there is no OS crash or userland core to attach to
    this is going to be an empty drgn.Program and integration tests will be
    skipped (e.g. only unit tests will run).
    """
    prog = drgn.Program()

    dump = get_crash_dump_path()
    if dump:
        prog.set_core_dump(dump)
        assert get_vmlinux_path()
        debug_info = (
            p
            for p in [get_vmlinux_path(), get_modules_dir()]
            if p is not None)
        load_debug_info(prog, list(debug_info))
        return prog

    dump = get_core_dump_path()
    if dump:
        prog.set_core_dump(dump)
        debug_info = (p for p in [
            get_binary_dir(),
            get_libs_path(),
            get_libs64_path(),
            get_lib_debug_info_path()
        ] if p is not None)
        load_debug_info(prog, list(debug_info))

    return prog


TEST_PROGRAM = setup_target()
TEST_REPL = REPL(TEST_PROGRAM, list(sdb.get_registered_commands().keys()))


def repl_invoke(cmd: str) -> int:
    """
    Accepts a command/pipeline in string form and evaluates
    it returning the exit code of the evaluation emulating
    the SDB repl.
    """
    assert TEST_PROGRAM
    sdb.target.set_prog(TEST_PROGRAM)
    sdb.register_commands()
    return TEST_REPL.eval_cmd(cmd)


def sdb_invoke(objs: Iterable[drgn.Object], line: str) -> Iterable[drgn.Object]:
    """
    Dispatch to sdb.invoke, but also drain the generator it returns, so
    the tests can more easily access the returned objects.

    This method is preferred over repl_invoke() when the test wants to
    do fancier checks by mocking a few objects that are later passed
    down to the pipeline. Other scenarios include but are not limited
    to testing that specific exceptions are thrown or analyzing internal
    state of objects that is not part of the output in stdout.
    """
    assert TEST_PROGRAM
    sdb.target.set_prog(TEST_PROGRAM)
    sdb.register_commands()
    return list(sdb.invoke(objs, line))


def slurp_output_file(dump_name: str, modname: str, cmd: str) -> str:
    """
    Given a module name and a command, find the output file
    and return all of its contents as a string.
    """
    # The pylint below is a false positive
    # pylint: disable=unspecified-encoding
    return Path(f"{TEST_OUTPUT_DIR}/{dump_name}/{modname}/{cmd}").read_text()


def generate_output_for_commands(cmds: List[str], dirpath: str) -> None:
    """
    Takes a list of SDB commands in string form, invokes them in the
    context of the current crash dump/sdb.REPL, and stores their output
    in the directory specified, each under a different file.

    Note: Keep in mind that if the directory specified exists then
    it will be removed together with all of its contents.
    """
    assert TEST_PROGRAM
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)
    os.makedirs(dirpath)
    for cmd in cmds:
        with open(f"{dirpath}/{cmd}", 'w', encoding="utf-8") as f:
            with redirect_stdout(f):
                repl_invoke(cmd)


def generate_output_for_test_module(dump_name: str, modname: str) -> None:
    """
    Generates the regression output for all the commands of
    a test module given  module name. The assumption for this
    to work automatically is that for the given modname "mod"
    there exist a test module under test.integration named
    test_mod_generic which has a list of commands in string
    form called CMD_TABLE.
    """
    test_mod = import_module(f"tests.integration.test_{modname}_generic")
    generate_output_for_commands(
        test_mod.CMD_TABLE,  # type: ignore[attr-defined]
        f"{TEST_OUTPUT_DIR}/{dump_name}/{modname}")
    print(f"Generated regression test output for {modname}...")


def get_all_generic_test_modules() -> List[str]:
    """
    Look at this current directory and capture all modules
    with generic capsys tests whose filename follows the
    'test_{module name}_generic.py' convention.
    """
    modnames = []
    for filename in os.listdir(THIS_DIR):
        m = re.search('test_(.+?)_generic.py', filename)
        if m:
            modnames.append(m.group(1))
    return modnames


def generate_known_regression_output(dump_name: str) -> None:
    """
    Auto-generate the baseline regression output for all
    the detected test modules in this directory.
    """
    for modname in get_all_generic_test_modules():
        generate_output_for_test_module(dump_name, modname)
