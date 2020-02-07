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
    # addr
    "addr spa_namespace_avl",
    "addr spa_namespace_avl | deref",
    "addr spa_namespace_avl | deref | addr",

    # array
    "spa | member spa_zio_taskq[0][0].stqs_taskq | array 2",
    "zfs_dbgmsg | head 1 | member zdm_msg | array",
    "zfs_dbgmsg | head 1 | member zdm_msg | array 2",
    "zfs_dbgmsg | head 1 | member zdm_msg | array -1",
    "zfs_dbgmsg | head 1 | member zdm_msg | array 0",
    #
    # bad dereferences with array:
    # The following test case for array semantically belongs
    # to NEG_CMDS. That said, see similar comment for the
    # member command on why the following command is listed
    # here.
    #
    # [neg] array passed a NULL-pointer array
    "echo 0x0 | cast int * | array 1",

    # deref
    "addr jiffies | deref",

    # filter - no input
    "filter obj == 1",
    # filter - match
    "echo 0x0 | filter obj == 0",
    # filter - no match
    "echo 0x0 | filter obj == 1",
    # filter - identity
    "echo 0x1 | filter obj == obj",
    # filter - multiple entries match one (eq)
    "echo 0x0 0x1 0x2 | filter obj == 1",
    # filter - multiple entries match one (gt)
    "echo 0x0 0x1 0x2 | filter obj > 1",
    # filter - multiple entries match one (ge)
    "echo 0x0 0x1 0x2 | filter obj >= 1",
    # filter - multiple entries match one (lt)
    "echo 0x0 0x1 0x2 | filter obj < 1",
    # filter - multiple entries match one (le)
    "echo 0x0 0x1 0x2 | filter obj <= 1",
    # filter - deref member
    "spa rpool | filter obj.spa_syncing_txg == 1624 | member spa_name",
    "spa rpool | filter obj.spa_syncing_txg >= 1624 | member spa_name",
    "spa rpool | filter obj.spa_syncing_txg <= 1624 | member spa_name",
    "spa rpool | filter obj.spa_syncing_txg < 1624 | member spa_name",
    "spa rpool | filter obj.spa_syncing_txg > 1624 | member spa_name",

    # member - generic
    "member no_object",
    "addr spa_namespace_avl | member avl_root->avl_child[0]->avl_child",
    "addr spa_namespace_avl | member avl_root.avl_child[0].avl_child",
    "spa | member spa_ubsync.ub_rootbp.blk_dva[0].dva_word",
    "addr spa_namespace_avl | member avl_root.avl_pcb avl_size",
    "spa | head 1 | member spa_zio_taskq[0][0].stqs_taskq",
    "spa | head 1 | member spa_zio_taskq[0][0].stqs_taskq[0]",
    # member - forcing printing beyond the bounds of the array (pointer)
    "addr spa_namespace_avl | member avl_root->avl_child[3]",
    "zfs_dbgmsg | head 1 | member zdm_msg[2]",
    #
    # bad dereferences with member:
    # The following test cases for member semantically belong
    # to NEG_CMDS. That said, we add them here because their
    # exit code is actually 0. The reason for this is explained
    # on the comment within the _call() method of the command,
    # where we prefer just throwing warning (as opposed to errors
    # and then halting) when dereferencing bad addresses to make
    # pipelines that use member more usable (please refer to
    # SingleInputCommad class for more info).
    #
    "echo 0x0 | cast spa_t * | member spa_name",
    "echo 0x1234 | cast dmu_recv_cookie_t * | member drc_os",
    # member - bad and good pointer combination (e.g. doesn't blow up)
    "echo 0x0 | addr spa_namespace_avl | echo 0x1 | cast avl_tree_t * | member avl_root",

    # print
    "addr spa_namespace_avl | print",
    "addr spa_namespace_avl | print -n",
    "addr spa_namespace_avl | print -r",
    "addr spa_namespace_avl | print -nr",
    "addr spa_namespace_avl | print -R",
    "addr spa_namespace_avl | deref | print",
    "addr spa_namespace_avl | print -d",
    "addr spa_namespace_avl zfs_dbgmsgs | print -d",
    "spa | head 1 | member spa_name[1] | print",
    "spa | head 1 | member spa_name[1] | print -c",
    "spa | head 1 | member spa_name[1] | print -cr",
    "spa | head 1 | deref | print -rs",
    "spa | head 1 | deref | print -Rs",

    # ptype
    "ptype spa_t",
    "ptype spa vdev",
    "ptype zfs_case v_t thread_union",
]

NEG_CMDS = [
    # addr
    "addr bogus",

    # array needs number of elements for pointer arrays
    "spa | member spa_zio_taskq[0][0].stqs_taskq | array",
    # array passed non-pointer type
    "echo 1234 | cast int | array",
    # array passed a "pointer" array that is of type void (e.g. incomplete)
    "echo 0x0 | cast void * | array 1",

    # dereference void *
    "echo 0xffff90cc11b28000 | deref",
    # dereference NULL
    "echo 0x0 | cast int * | deref",
    # dereference other invalid memory location
    "echo 0x10 | cast int * | deref",
    # dereference non-pointer type
    "addr jiffies | deref | deref",

    # filter - no right-hand side
    "zfs_dbgmsg | filter obj ==",
    # filter - no left-hand side
    "zfs_dbgmsg | filter  == obj",
    # filter - no operator
    "zfs_dbgmsg | filter obj"
    # filter - bogus member
    "spa rpool | filter obj.bogus == 1624",
    # filter - bogus op
    "spa rpool | filter obj.spa_syncing_txg bogus_op 1624",

    # member user arrow notation in embedded struct member
    "spa | member spa_ubsync->ub_rootbp",
    # member - bogus member
    "spa | member spa_ubsync.bogus",
    # member - incomplete array expression
    "addr spa_namespace_avl | member avl_root->avl_child[1",
    # member - bogus array index
    "addr spa_namespace_avl | member avl_root->avl_child[a]",
    # member - incomplete expression
    "spa | member spa_zio_taskq[0][0].stqs_taskq->",
    # member - incomplete expression
    "spa | member spa_zio_taskq[0][0].stqs_taskq.",

    # ptype - bogus type
    "ptype bogus_t",
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
