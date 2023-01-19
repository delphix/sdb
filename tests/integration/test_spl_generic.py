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

from typing import Any
import os.path

import pytest
from tests.integration.infra import repl_invoke, get_crash_dump_path, slurp_output_file

CMD_TABLE = [
    # avl walker
    "addr spa_namespace_avl | avl",
    "addr spa_namespace_avl | walk",
    "addr arc_mru | member [0].arcs_list[1] | walk | head",

    # multilist walker
    "addr arc_mru | member [0].arcs_list[1] | multilist | head",

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
]


@pytest.mark.skipif(  # type: ignore[misc]
    not get_crash_dump_path(),
    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', CMD_TABLE)  # type: ignore[misc]
def test_cmd_output_and_error_code(capsys: Any, cmd: str) -> None:
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    dump_path = get_crash_dump_path()
    assert dump_path is not None
    dump_name = os.path.basename(dump_path)
    assert captured.out == slurp_output_file(dump_name, "spl", cmd)
