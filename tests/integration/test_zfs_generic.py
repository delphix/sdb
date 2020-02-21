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

CMD_TABLE = [
    "arc",
    "dbuf",
    "spa",
    "spa -v",
    "spa rpool",
    "spa | pp",
    "spa | head 1 | spa",
    "spa | vdev",
    "spa | vdev | pp",
    "spa | vdev | metaslab",
    "spa | vdev | metaslab -w",
    "spa | vdev | metaslab | member ms_allocatable | range_tree",
    "spa | vdev | metaslab | member ms_allocatable.rt_root | zfs_btree",
    "zfs_dbgmsg",
    "zfs_dbgmsg | tail 5 | zfs_dbgmsg",
    "dbuf -l 1",
    "dbuf | dbuf -l 1",
    'dbuf | dbuf -l 1 | head | dbuf'
] # yapf: disable


@pytest.mark.skipif(not dump_exists(),
                    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', CMD_TABLE)
def test_cmd_output_and_error_code(capsys, cmd):
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    assert captured.out == slurp_output_file("zfs", cmd)
