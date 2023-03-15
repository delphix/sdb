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
# pylint: disable=missing-function-docstring
# pylint: disable=line-too-long

import datetime
import re
from typing import Any, List, Tuple
import os.path

import pytest
from tests.integration.infra import repl_invoke, get_crash_dump_path, slurp_output_file

POS_CMDS_201912060006 = [
    # multilist walker
    "addr arc_mru | member [0].arcs_list[1] | walk | head",
    "addr arc_mru | member [0].arcs_list[1] | multilist | head",
]

POS_CMDS = [
    # avl walker
    "addr spa_namespace_avl | avl",
    "addr spa_namespace_avl | walk",

    # multilist walker
    "spa | member spa_normal_class.mc_metaslab_txg_list | multilist",
    "spa | member spa_normal_class.mc_metaslab_txg_list | walk",

    # spl_cache walker
    'spl_kmem_caches | filter \'obj.skc_name == "ddt_cache"\' | walk',
    "spl_kmem_caches | filter 'obj.skc_linux_cache == 0' | spl_cache",
    "spl_kmem_caches | filter 'obj.skc_linux_cache == 0' | spl_cache | cnt",
    # spl_cache - ensure we can walk caches backed by SLUB
    "spl_kmem_caches | filter 'obj.skc_linux_cache > 0' | filter 'obj.skc_obj_alloc > 0' | head 1 | spl_cache",

    # spl_kmem_caches
    "spl_kmem_caches",
    "spl_kmem_caches -o name,source",
    "spl_kmem_caches -v",
    "spl_kmem_caches -s entry_size",
    "spl_kmem_caches -o name,entry_size -s entry_size",
    "spl_kmem_caches -s entry_size | head 4 | spl_kmem_caches",
    "spl_kmem_caches | pp",

    # spl_list walker
    "spa | member spa_config_list | spl_list",
    "spa | member spa_config_list | walk",
    "spa | member spa_evicting_os_list | spl_list",
    "spa | member spa_evicting_os_list | walk",
]

NEG_CMDS: List[str] = []

CMD_TABLE = POS_CMDS + NEG_CMDS + POS_CMDS_201912060006

POS_CMDS_HISTORY = [('201912060006', POS_CMDS_201912060006)]


def crash_get_cmds() -> Tuple[List[str], List[str]]:
    """
    Returns a tuple with the right list of commands to be tested
    based on the crash dump's date. The first element of the tuple
    is the list of commands we expect to succeed and the second
    element the list we expect to fail.
    """
    dump_path = get_crash_dump_path()
    assert dump_path is not None

    dump_name = os.path.basename(dump_path)
    m = re.match(r"dump.(\d+)", dump_name)
    assert m is not None

    dt_str = m.group(1)
    dt = datetime.datetime.strptime(dt_str, '%Y%m%d%H%M')
    pos_cmds = POS_CMDS
    neg_cmds = NEG_CMDS
    for date_str, cmds in POS_CMDS_HISTORY:
        date = datetime.datetime.strptime(date_str, '%Y%m%d%H%M')
        if date < dt:
            neg_cmds.extend(cmds)
        else:
            pos_cmds.extend(cmds)
    return pos_cmds, neg_cmds


@pytest.mark.skipif(  # type: ignore[misc]
    not get_crash_dump_path(),
    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', crash_get_cmds()[0])  # type: ignore[misc]
def test_cmd_output_and_error_code_0(capsys: Any, cmd: str) -> None:
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    dump_path = get_crash_dump_path()
    assert dump_path is not None
    dump_name = os.path.basename(dump_path)
    assert captured.out == slurp_output_file(dump_name, "spl", cmd)


@pytest.mark.skipif(  # type: ignore[misc]
    not get_crash_dump_path(),
    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', crash_get_cmds()[1])  # type: ignore[misc]
def test_cmd_output_and_error_code_1(capsys: Any, cmd: str) -> None:
    assert repl_invoke(cmd) == 1
    captured = capsys.readouterr()
    dump_path = get_crash_dump_path()
    assert dump_path is not None
    dump_name = os.path.basename(dump_path)
    assert captured.out == slurp_output_file(dump_name, "spl", cmd)
