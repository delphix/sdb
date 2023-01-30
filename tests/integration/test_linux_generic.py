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

POS_CMDS = [
    # container_of
    "addr init_task | member comm | addr | container_of task_struct comm | cast void *",

    # cpu_counter_sum
    "addr vm_committed_as | cpu_counter_sum",
    "addr tcp_orphan_count | cpu_counter_sum",
    "addr tcp_sockets_allocated | cpu_counter_sum",

    # crashed_thread
    "crashed_thread",
    "crashed_thread | stacks",

    # percpu
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu',
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 0',
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 1',
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 0 1',

    # fget
    "find_task 1 | fget 1 4",
    "find_task 1 | fget 1 4 123123",

    # find_task
    "find_task 1",
    "find_task 1 2",
    "find_task 1 2 | member comm",

    # lxhlist
    "addr init_task | member thread_pid.tasks[3] | lxhlist task_struct pid_links[3] | member comm",

    # lxlist
    "addr modules | lxlist module list | member name",

    # pid
    "pid 1",
    "pid 1 10 12437",

    # rbtree
    "addr vmap_area_root | rbtree vmap_area rb_node",

    # slabs
    "slabs",
    "slabs -v",
    "slabs -s util",
    'slabs -s active_objs -o active_objs,util,name',
    "slabs | pp",
    "slabs -s util | slabs",
    "slabs | head 2 | slabs",

    # slub
    'slabs | filter \'obj.name == "zio_cache"\' | slub_cache',
    'slabs | filter \'obj.name == "zio_cache"\' | walk',
    'slabs | filter \'obj.name == "zio_cache"\' | slub_cache | count',
    'slabs | filter \'obj.name == "zio_cache"\' | slub_cache | cast zio_t * | member io_spa.spa_name',
    # slub - expected inconsistent freelist test
    # (still a positive tests because we want to keep going besides inconsistencies)
    'slabs | filter \'obj.name == "UNIX"\' | slub_cache | count',

    # stacks
    "stacks",
    "stacks -a",
    "stacks -m zfs",
    "stacks -c spa_sync",
    "stacks -m zfs -c spa_sync",
    "stacks -m zfs -c zthr_procedure",
    'threads | filter \'obj.comm == "java"\' | stack',
    "stacks -m zfs | count",
    "echo 0xffffa089669edc00 | stack",

    # threads
    "threads",
    "threads | count",
    'threads | filter \'obj.comm == "java"\' | threads',
    "thread",

    # whatis
    "dbuf |head 1 |deref |member db_buf |whatis",
    "whatis 0xffffa089407ca870",
    "whatis 0xffffa0888c766000 0xffffa089407ca870",
    "whatis 0xffff",
    "whatis 0xf987kkbbh"
]

STRIPPED_POS_CMDS = [
    # dmesg
    "dmesg",
    "dmesg | pp",
    "dmesg | filter 'obj.level == 3' | dmesg",
]

NEG_CMDS = [
    # container_of
    "addr init_task | member comm | addr | container_of task_struct bogus_member | cast void *",
    "addr init_task | member comm | addr | container_of bogus_type comm | cast void *",
    # not passing pointer - skips addr command in pipe
    "addr init_task | member comm | container_of task_struct comm | cast void *",
    # using a scalar type instead of composite (structure, etc..)
    "addr init_task | member comm | addr | container_of int comm | cast void *",
    # using an incorrect structure
    "addr init_task | member comm | addr | container_of pid comm | cast void *",

    # cpu_counter_sum
    "echo 0x0 | cpu_counter_sum",
    "addr spa_namespace_avl | cpu_counter_sum",

    # lxhlist
    "addr init_task | member thread_pid.tasks[3] | lxhlist bogus_type pid_links[3] | member comm",
    "addr init_task | member thread_pid.tasks[3] | lxhlist task_struct bogus_member | member comm",

    # lxlist
    "addr modules | lxlist bogus_type list | member name",
    "addr modules | lxlist module bogus_member | member name",

    # percpu - not valid CPU number
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 2',
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 3',
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 100',
    'slabs | filter \'obj.name == "kmalloc-8"\' | member cpu_slab | percpu 0 2 1',

    # rbtree
    "addr vmap_area_root | rbtree bogus_type rb_node",
    "addr vmap_area_root | rbtree vmap_area bogus_member",

    # slabs
    "slabs -s bogus",
    "slabs -o bogus",
    "slabs -s active_objs -o util",

    # stacks
    "stacks -m bogus",
    "stacks -c bogus",
    "stacks -t bogus",
    "stacks -m bogus | count",
]

CMD_TABLE = POS_CMDS + STRIPPED_POS_CMDS + NEG_CMDS


@pytest.mark.skipif(  # type: ignore[misc]
    not get_crash_dump_path(),
    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', POS_CMDS)  # type: ignore[misc]
def test_cmd_output_and_error_code_0(capsys: Any, cmd: str) -> None:
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    dump_path = get_crash_dump_path()
    assert dump_path is not None
    dump_name = os.path.basename(dump_path)
    assert captured.out == slurp_output_file(dump_name, "linux", cmd)


@pytest.mark.skipif(  # type: ignore[misc]
    not get_crash_dump_path(),
    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', NEG_CMDS)  # type: ignore[misc]
def test_cmd_output_and_error_code_1(capsys: Any, cmd: str) -> None:
    assert repl_invoke(cmd) == 1
    captured = capsys.readouterr()
    dump_path = get_crash_dump_path()
    assert dump_path is not None
    dump_name = os.path.basename(dump_path)
    assert captured.out == slurp_output_file(dump_name, "linux", cmd)


@pytest.mark.skipif(  # type: ignore[misc]
    not get_crash_dump_path(),
    reason="couldn't find crash dump to run tests against")
@pytest.mark.parametrize('cmd', STRIPPED_POS_CMDS)  # type: ignore[misc]
def test_cmd_stripped_output_and_error_code_0(capsys: Any, cmd: str) -> None:
    assert repl_invoke(cmd) == 0
    captured = capsys.readouterr()
    dump_path = get_crash_dump_path()
    assert dump_path is not None
    dump_name = os.path.basename(dump_path)
    slurped = slurp_output_file(dump_name, "linux", cmd)
    for i, n in enumerate(captured.out):
        assert n.strip() == slurped[i].strip()
    assert len(captured.out) == len(slurped)
