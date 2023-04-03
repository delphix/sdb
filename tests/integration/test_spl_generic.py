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

from typing import Any, List

import pytest
from tests.integration.infra import get_crash_dump_dir_paths, get_all_reference_crash_dumps, RefDump

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


@pytest.mark.skipif(  # type: ignore[misc]
    len(get_crash_dump_dir_paths()) == 0,
    reason="couldn't find any crash/core dump to run tests against")
@pytest.mark.parametrize('rdump',
                         get_all_reference_crash_dumps())  # type: ignore[misc]
@pytest.mark.parametrize('cmd', CMD_TABLE)  # type: ignore[misc]
def test_cmd_output_and_error_code(capsys: Any, rdump: RefDump,
                                   cmd: str) -> None:
    rdump.verify_cmd_output_and_code(capsys, "spl", cmd)
