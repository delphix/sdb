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
import drgn.helpers.linux.fs as drgn_fs
import sdb


class FGet(sdb.SingleInputCommand):
    """
    Return "struct file *" given the FD number for each task_struct piped as input.

    EXAMPLES
        Print "struct file *" FDs 1 and 4 for the task struct with PID 1

           sdb> find_task 1 | fget 1 4
            (struct file *)0xffff944ede98ab00
            (struct file *)0xffff944ee5476f00
    """

    names = ["fget"]
    input_type = "struct task_struct *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("fd",
                            type=int,
                            nargs="+",
                            help="numeric FD(s) of task_struct")
        return parser

    def _call_one(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        for fd in self.args.fd:
            yield drgn_fs.fget(obj, fd)
