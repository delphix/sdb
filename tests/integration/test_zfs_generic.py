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
    # arc
    "arc",

    # blkptr
    "spa | head 1 | deref |member spa_uberblock | member ub_rootbp | blkptr",
    "dbuf | head 1 | member db_blkptr | blkptr",

    # dbuf
    "dbuf",
    "dbuf -l 1",
    "dbuf | dbuf -l 1",
    'dbuf | dbuf -l 1 | head | dbuf',

    # spa + vdev + metaslab
    "spa",
    "spa -H",
    "spa -v",
    "spa -vH",
    "spa -vm",
    "spa -vmH",
    "spa -mH",
    "spa rpool",
    "spa | pp",
    "spa | head 1 | spa",
    "spa | vdev",
    "spa | vdev | pp",
    "spa | vdev | metaslab",
    "spa | vdev | metaslab -w",
    "spa | vdev | metaslab | member ms_allocatable | range_tree",
    "spa | vdev | metaslab | member ms_allocatable.rt_root | zfs_btree",

    # zfs_dbgmsg
    "zfs_dbgmsg",
    "zfs_dbgmsg | tail 5 | zfs_dbgmsg",

    # zfs_histogram
    "spa data | member spa_normal_class.mc_histogram | zfs_histogram",
    "spa data | vdev | metaslab | filter 'obj.ms_loaded == 1' | head 1 | member ms_sm.sm_phys.smp_histogram | zhist",
    "spa data | vdev | metaslab | filter 'obj.ms_loaded == 1' | head 1 | member ms_sm.sm_phys.smp_histogram | zhist 9",
    "spa data | vdev | metaslab | filter 'obj.ms_loaded == 1' | head 1 | member ms_allocatable.rt_histogram | zhist",

    # zio
    "zio",
    "zio -r",
] # yapf: disable


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
    assert captured.out == slurp_output_file(dump_name, "zfs", cmd)
