#
# Copyright 2019 Delphix
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
DUMP_PATH = f"{DATA_DIR}/dump.201912060006"
MODS_PATH = f"{DATA_DIR}/mods"
VMLX_PATH = f"{DATA_DIR}/vmlinux-5.0.0-36-generic"
TEST_OUTPUT_DIR = f"{DATA_DIR}/regression_output"


def dump_exists() -> bool:
    """
    Used as the sole indicator of whether the integration
    tests will run.
    """
    return os.path.exists(DUMP_PATH) and os.path.exists(
        MODS_PATH) and os.path.exists(VMLX_PATH)


def setup_target() -> Optional[drgn.Program]:
    """
    Create a drgn.Program instance and setup the SDB
    context for all the integration tests. If there
    is no crash dump to attach to this is going to
    be an empty drgn.Program.
    """
    prog = drgn.Program()
    if not dump_exists():
        return prog
    prog.set_core_dump(DUMP_PATH)
    load_debug_info(prog, [VMLX_PATH, MODS_PATH])
    return prog


TEST_PROGRAM = setup_target()
TEST_REPL = REPL(TEST_PROGRAM, sdb.get_registered_commands())


def repl_invoke(cmd: str) -> int:
    """
    Accepts a command/pipeline in string form and evaluates
    it returning the exit code of the evaluation emulating
    the SDB repl.
    """
    assert TEST_PROGRAM
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
    return list(sdb.invoke(TEST_PROGRAM, objs, line))


def slurp_output_file(modname: str, cmd: str) -> str:
    """
    Given a module name and a command, find the output file
    and return all of its contents as a string.
    """
    return Path(f"{TEST_OUTPUT_DIR}/{modname}/{cmd}").read_text()


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
        with open(f"{dirpath}/{cmd}", 'w') as f:
            with redirect_stdout(f):
                repl_invoke(cmd)


def generate_output_for_test_module(modname: str) -> None:
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
        f"{TEST_OUTPUT_DIR}/{modname}")
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


def generate_known_regression_output():
    """
    Auto-generate the baseline regression output for all
    the detected test modules in this directory.
    """
    for modname in get_all_generic_test_modules():
        generate_output_for_test_module(modname)
