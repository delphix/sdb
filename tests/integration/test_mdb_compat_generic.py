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
Integration tests for mdb compatibility syntax.

These tests verify that mdb-style commands (symbol::cmd) produce the same
output as their sdb equivalents (addr symbol | cmd).
"""

from typing import Any

import pytest
from tests.integration.infra import get_crash_dump_dir_paths, get_all_reference_crash_dumps, RefDump

# Positive test cases - mdb-style syntax that should work
POS_CMDS = [
    # Basic mdb syntax: symbol::command
    # Equivalent to: addr spa_namespace_avl | walk
    "spa_namespace_avl::walk",

    # mdb syntax with command arguments
    # Equivalent to: addr spa_namespace_avl | print -nr
    "spa_namespace_avl::print -nr",

    # mdb syntax with hex address
    # Equivalent to: addr jiffies | deref
    "jiffies::deref",

    # mdb syntax with pipes
    # Equivalent to: addr spa_namespace_avl | walk | head 2
    "spa_namespace_avl::walk | head 2",
]

# Negative test cases - commands that should produce errors
# These help verify error messages are clear and useful
NEG_CMDS = [
    # Multiple :: in first segment - 'print::head' will fail as unknown command
    "spa::print::head",

    # Triple colon - ':cmd' will fail command name validation
    "arg:::cmd",

    # Invalid symbol
    "bogus_nonexistent_symbol::print",

    # Note: "spa::" (empty command) is tested in unit tests only because it
    # produces an internal error with platform-dependent output formatting
]

CMD_TABLE = POS_CMDS + NEG_CMDS


@pytest.mark.skipif(
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dumps to run tests against")
@pytest.mark.parametrize('rdump', get_all_reference_crash_dumps())
@pytest.mark.parametrize('cmd', CMD_TABLE)
def test_cmd_output_and_error_code(capsys: Any, rdump: RefDump,
                                   cmd: str) -> None:
    rdump.verify_cmd_output_and_code(capsys, "mdb_compat", cmd)
