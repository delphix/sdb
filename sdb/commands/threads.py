#
# Copyright 2020 Delphix
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

from typing import Iterable

import drgn
from drgn.helpers.linux.pid import for_each_task

import sdb
from sdb.commands.internal.table import Table
from sdb.commands.stacks import Stacks


class Threads(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate and print information about threads (task_stuct)

    COLUMNS
        task - address of the task_struct
        state - the state of the thread
        pid - the pid of the thread's process
        prio - the priority of the thread
        comm - the thread's command

    EXAMPLE
        sdb> threads | filter obj.comm == "java" | threads
        task               state         pid  prio comm
        ------------------ ------------- ---- ---- ----
        0xffff95d48b0e8000 INTERRUPTIBLE 4386 120  java
        0xffff95d48b0e96c0 INTERRUPTIBLE 4388 120  java
        0xffff95d48b0ead80 INTERRUPTIBLE 4387 120  java
        0xffff95d48b0edb00 INTERRUPTIBLE 4304 120  java
        0xffff95d4af20ad80 INTERRUPTIBLE 4395 120  java
    """

    names = ["threads", "thread"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"

    FIELDS = {
        "task": lambda obj: hex(obj.value_()),
        "state": lambda obj: str(Stacks.task_struct_get_state(obj)),
        "pid": lambda obj: int(obj.pid),
        "prio": lambda obj: int(obj.prio),
        "comm": lambda obj: str(obj.comm.string_().decode("utf-8")),
    }

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        fields = list(Threads.FIELDS.keys())
        table = Table(fields, None, {"task": str})
        for obj in objs:
            row_dict = {field: Threads.FIELDS[field](obj) for field in fields}
            table.add_row(row_dict["task"], row_dict)
        table.print_()

    def no_input(self) -> Iterable[drgn.Object]:
        yield from for_each_task(sdb.get_prog())
