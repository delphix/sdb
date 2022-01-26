#
# Copyright 2021 Datto, Inc.
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

# pylint: disable=missing-docstring

import drgn
from drgn.helpers.linux.pid import pid_task
import sdb
from sdb.commands.zfs.zfs_refcount import Zfs_Refcount
from sdb.commands.linux.process import Process


class Rrw_lock(sdb.PrettyPrinter):
    """
    DESCRIPTION

    Depending on the debug settings, readers may be anonymous. In this case
    we only can print the count of readers.  If reference_tracking_enabled was
    set, we can display the function(s) holding the read lock.

    The thread actively holding RW_WRITER will be displayed, if any, and
    we search the process table to print threads with rrw_enter_write in their
    stack (if they are trying to enter the rrwlock in question).

    EXAMPLES

    spa | member spa_dsl_pool |member dp_config_rwlock | rrwlock
    writer wanted?:   (boolean_t)B_FALSE
    --------------------------------
    <PID, command line  and stacks of any thread(s) waiting for this writer lock>
    ...
    <PID, command line, and stack of thread holding this writer lock>
    ...
    anonymous readers:
        zfs_refcount_t at 0xffff9dd55f5c0748 has 0 current holds tracked=1
    linked readers:
        zfs_refcount_t at 0xffff9dd55f5c07d0 has 0 current holds tracked=1

    """

    names = ["rrwlock"]
    input_type = "rrwlock_t *"
    output_type = "rrwlock_t *"

    @staticmethod
    def print_writer_wanted_stacks(rrw: drgn.Object, indent: int,
                                   exclude: int) -> None:
        prog = sdb.get_prog()
        for pid in Process().all():
            try:
                task = pid_task(pid, 0)
                if sdb.is_null(task):
                    continue
                cur_pid = task.pid
                trace = prog.stack_trace(task)
            except ValueError:
                continue
            # we will print the task holding the write lock later
            if exclude != -1 and cur_pid == exclude:
                continue
            for frame in trace:
                if frame.name == 'rrw_enter_write':
                    if frame['rrl'] == rrw:
                        Process(task.pid).print_process(indent)
                        continue

    def pretty_print(self, objs: drgn.Object) -> None:
        for rrw in objs:
            indent = 4
            print(f"writer wanted?:   {rrw.rr_writer_wanted}")
            exclude_pid = -1
            if not sdb.is_null(rrw.rr_writer):
                exclude_pid = int(rrw.rr_writer.pid)
            self.print_writer_wanted_stacks(rrw, indent, exclude_pid)
            print(f"writer thread_t*: {hex(int(rrw.rr_writer))}")
            if not sdb.is_null(rrw.rr_writer):
                Process(rrw.rr_writer.pid).print_process(indent)
            print("anonymous readers:")
            Zfs_Refcount().print_one(
                sdb.create_object('zfs_refcount_t *',
                                  rrw.rr_anon_rcount.address_of_()), indent)
            print("linked readers:")
            Zfs_Refcount().print_one(
                sdb.create_object('zfs_refcount_t *',
                                  rrw.rr_linked_rcount.address_of_()), indent)
