#
# Copyright 2021 Datto Inc.
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

import datetime
import argparse
from typing import Callable, Dict, Iterable, List, Union

import drgn
from drgn.helpers.linux.pid import for_each_task

import sdb
from sdb.commands.stacks import Stacks
from sdb.commands.threads import Threads


class Ps(Threads):
    """
    Locate and print information about processes

    POTENTIAL COLUMNS
        task - address of the task_struct
        uid  - user id
        pid  - the pid of the thread's process
        time - cumulative CPU time, "[DD-]HH:MM:SS" format
        state - the state of the thread
        prio - the priority of the thread
        comm - the thread's command
        cmdline - the thread's command line (when available)

    EXAMPLE
        sdb> ps -e
        task               uid  pid  time    stime   ppid  cmd
        ------------------ ---- ---- ------- ------- ----- ----------------
        0xffff9995001a0000 1000 4387 0:00:00 0:00:00 1218  inotify_reader
        0xffff9995001a2d00 1000 4382 0:00:00 0:00:00 1218  slack
        0xffff9995001a4380 1000 4383 0:00:04 0:00:00 1218  slack
        0xffff9995001a5a00 1000 4554 0:11:00 0:09:56 4118  AudioIP~ent RPC
        0xffff99950a430000 1000 4284 0:00:00 0:00:00 4118  HTML5 Parser
        0xffff99950a431680 1000 4157 0:00:12 0:00:08 1218  localStorage DBa
        ...
    """

    names = ["ps"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"

    FIELDS: Dict[str, Callable[[drgn.Object], Union[str, int]]] = {
        "task":
            lambda obj: hex(obj.value_()),
        "uid":
            lambda obj: int(obj.real_cred.uid.val),
        "pid":
            lambda obj: int(obj.pid),
        "time":
            lambda obj: str(
                datetime.timedelta(seconds=int(obj.utime) / 1000 / 1000)),
        "stime":
            lambda obj: str(
                datetime.timedelta(seconds=int(obj.stime) / 1000 / 1000)),
        "ppid":
            lambda obj: int(obj.parent.pid),
        "stat":
            lambda obj: str(Stacks.task_struct_get_state(obj)),
        "cmd":
            lambda obj: str(obj.comm.string_().decode("utf-8")),
    }

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument('-e', '--every', action='store_true', \
                help="Select all processes. Identical to -A")
        parser.add_argument('-A', '--all', action='store_true', \
                help="Select all processes. Identical to -e")
        parser.add_argument('-C', '--C', type=str, \
                help="Print only the process IDs of a command")
        parser.add_argument('-x', '--x', action='store_true', \
                help="Show PID, TIME, CMD")
        parser.add_argument('--no-headers', '--no-heading', \
                action='store_true', \
                help="Show the output without headers.")
        parser.add_argument('-p', '--pid', type=int, nargs="+", \
                help="Select by process ID. Identical to --pid.")
        parser.add_argument('-P', '--ppid', type=int, nargs="+", \
                help="Select by parent process ID.  \
                      This selects the processes with \
                      a parent process ID in the pid list."
                    )
        parser.add_argument('-o',
                            '--format',
                            type=str,
                            help="User-defined format. \
                            format is a single argument in the form of a blank-separated \
                            or comma-separated list, which offers a way to specify individual\
                            output columns. Headers may be renamed (ps -o pid,ppid) as desired.  "
                           )
        return parser

    def get_table_key(self) -> str:
        return "pid"

    def get_filtered_fields(self) -> List[str]:
        fields = list(self.FIELDS.keys())
        fields_option_ae = [
            x for x in fields if x in "task, uid, pid, ppid, stime, time, cmd"
        ]
        fields_option_x = [x for x in fields if x in "pid, stat, time, cmd"]
        fields_option_default = [x for x in fields if x in "pid, time, cmd"]

        if self.args.every or self.args.all:
            fields = fields_option_ae
        elif self.args.x:
            fields = fields_option_x
        elif self.args.format:
            fields_option_o = 'task,' + self.args.format.lower()
            fields_option_o = [x for x in fields if x in fields_option_o]
            fields = fields_option_o
        else:
            fields = fields_option_default
        return fields

    def show_headers(self) -> bool:
        return not self.args.no_headers

    def no_input(self) -> Iterable[drgn.Object]:
        cmds = self.args.C.split(",") if self.args.C else []
        pids = self.args.pid if self.args.pid else []
        ppids = self.args.ppid if self.args.ppid else []
        for obj in for_each_task(sdb.get_prog()):
            if self.args.pid:
                if obj.pid not in pids:
                    continue
            if self.args.C:
                cmd = str(obj.comm.string_().decode("utf-8"))
                if cmd not in cmds:
                    continue
            if self.args.ppid:
                if obj.parent.pid not in ppids:
                    continue
            yield obj
