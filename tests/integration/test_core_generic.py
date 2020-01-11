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
# pylint: disable=missing-function-docstring

import pytest

from tests.integration.infra import repl_invoke, dump_exists, slurp_output_file

POS_CMDS = [
    "addr jiffies | deref",
]

NEG_CMDS = [
    # dereference void *
    "echo 0xffff90cc11b28000 | deref",
    # dereference NULL
    "echo 0x0 | cast int * | deref",
    # dereference other invalid memory location
    "echo 0x10 | cast int * | deref",
    # dereference non-pointer type
    "addr jiffies | deref | deref",
]

CMD_TABLE = POS_CMDS + NEG_CMDS


@pytest.mark.skipif(not dump_exists(),
                    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', POS_CMDS)
def test_cmd_output_and_error_code_0(capsys, cmd):
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    assert captured.out == slurp_output_file("core", cmd)


@pytest.mark.skipif(not dump_exists(),
                    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', NEG_CMDS)
def test_cmd_output_and_error_code_1(capsys, cmd):
    assert repl_invoke(cmd) == 1
    captured = capsys.readouterr()
    assert captured.out == slurp_output_file("core", cmd)
