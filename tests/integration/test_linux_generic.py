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
    "addr init_task | member thread_pid.tasks[3] | lxhlist task_struct pid_links[3] | member comm",
    "addr modules | lxlist module list | member name",
    "slabs",
    "slabs -v",
    "slabs -s util",
    'slabs -s active_objs -o "active_objs,util,name"',
    "slabs | pp",
    "slabs -s util | slabs",
    "slabs | head 2 | slabs",
    "stacks",
    "stacks -a",
    "stacks -m zfs",
    "stacks -c spa_sync",
    "stacks -m zfs -c spa_sync",
]

STRIPPED_POS_CMDS = [
    "dmesg",
    "dmesg | pp",
    "dmesg | filter obj.level == 3 | dmesg",
]

NEG_CMDS = [
    "addr init_task | member thread_pid.tasks[3] | lxhlist bogus_type pid_links[3] | member comm",
    "addr init_task | member thread_pid.tasks[3] | lxhlist task_struct bogus_member | member comm",
    "addr modules | lxlist bogus_type list | member name",
    "addr modules | lxlist module bogus_member | member name",
    "slabs -s bogus",
    "slabs -o bogus",
    "slabs -s active_objs -o util",
    "stacks -m bogus",
    "stacks -c bogus",
    "stacks -t bogus",
]

CMD_TABLE = POS_CMDS + STRIPPED_POS_CMDS + NEG_CMDS


@pytest.mark.skipif(not dump_exists(),
                    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', POS_CMDS)
def test_cmd_output_and_error_code_0(capsys, cmd):
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    assert captured.out == slurp_output_file("linux", cmd)


@pytest.mark.skipif(not dump_exists(),
                    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', NEG_CMDS)
def test_cmd_output_and_error_code_1(capsys, cmd):
    assert repl_invoke(cmd) == 1
    captured = capsys.readouterr()
    assert captured.out == slurp_output_file("linux", cmd)


@pytest.mark.skipif(not dump_exists(),
                    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', STRIPPED_POS_CMDS)
def test_cmd_stripped_output_and_error_code_0(capsys, cmd):
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    slurped = slurp_output_file("linux", cmd)
    for i in range(len(captured.out)):
        assert captured.out[i].strip() == slurped[i].strip()
    assert len(captured.out) == len(slurped)
