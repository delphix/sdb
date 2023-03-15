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

import argparse
from typing import Iterable

import drgn
from drgn.helpers.linux.pid import find_pid, find_task
import sdb


class FindPid(sdb.Command):
    """
    Return "struct pid *" for the given PID number in the global namespace.

    EXAMPLES
        Get the pid struct of the init process (PID 1):

            sdb> pid 1
            (struct pid *)0xffff944ee6d6a980
            sdb> pid 1 | deref
            (struct pid){
            .count = (refcount_t){
                    .refs = (atomic_t){
                            .counter = (int)50,
                    },
            },
            .level = (unsigned int)0,
            ...
    """

    names = ["pid"]
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("pid",
                            type=int,
                            nargs="+",
                            help="numeric PID(s) of process(es)")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for pid in self.args.pid:
            yield find_pid(sdb.get_prog(), pid)


class FindTask(sdb.Command):
    """
    Return "struct task_struct *" of the given PID number in the global namespace.

    EXAMPLES
        Get task_struct of PIDs 1 and 2:

            sdb> find_task 1 2
            (struct task_struct *)0xffff944ee6df1700
            (struct task_struct *)0xffff944ee6df2e00
            sdb> find_task 1 2 | member comm
            (char [16])"systemd"
            (char [16])"kthreadd"
    """

    names = ["find_task"]
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("pid",
                            type=int,
                            nargs="+",
                            help="numeric PID(s) of process(es)")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for pid in self.args.pid:
            yield find_task(sdb.get_prog(), pid)
