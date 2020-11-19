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

from textwrap import shorten
from typing import Callable, Dict, Iterable, Union

import drgn
from drgn.helpers.linux.pid import for_each_task
from drgn.helpers.linux.mm import cmdline

import sdb
from sdb.commands.internal.table import Table
from sdb.commands.stacks import Stacks


def _cmdline(obj: drgn.Object) -> str:
    try:
        s = " ".join(map(lambda s: s.decode("utf-8"), cmdline(obj)))

        #
        # The command line for a given thread can be obnoxiously long,
        # so (by default) we limit it to 50 characters here. This helps
        # preserve the readability of the command's output, but comes at
        # the cost of not always showing the full command line of a
        # thread.
        #
        return shorten(s, width=50)
    except drgn.FaultError:
        #
        # The command line information is contained in the user address
        # space of each thread, rather than in the kernel's address
        # space. Thus, often, it may not be possible to retreive the
        # thread's command line; e.g. when reading from a core dump.
        #
        return ""


class Threads(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate and print information about threads (task_stuct)

    COLUMNS
        task - address of the task_struct
        state - the state of the thread
        pid - the pid of the thread's process
        prio - the priority of the thread
        comm - the thread's command
        cmdline - the thread's command line (when available)

    EXAMPLE
        sdb> threads | filter 'obj.comm == "java"' | threads
        task               state         pid  prio comm cmdline
        ------------------ ------------- ---- ---- ---- ----------------------------------------
        0xffff8c96a7c70000 INTERRUPTIBLE 3029 120  java /usr/bin/java -Ddelphix.debug=true [...]
        0xffff8c96a7c71740 INTERRUPTIBLE 3028 120  java /usr/bin/java -Ddelphix.debug=true [...]
        0xffff8c96a7c75d00 INTERRUPTIBLE 3024 120  java /usr/bin/java -Ddelphix.debug=true [...]
        0xffff8c9715808000 INTERRUPTIBLE 3027 120  java /usr/bin/java -Ddelphix.debug=true [...]
    """

    names = ["threads", "thread"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"

    FIELDS: Dict[str, Callable[[drgn.Object], Union[str, int]]] = {
        "task": lambda obj: hex(obj.value_()),
        "state": lambda obj: str(Stacks.task_struct_get_state(obj)),
        "pid": lambda obj: int(obj.pid),
        "prio": lambda obj: int(obj.prio),
        "comm": lambda obj: str(obj.comm.string_().decode("utf-8")),
        "cmdline": _cmdline,
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
