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

#
# The pylint workaround below is for the example
# sections of the help messages.
#
# pylint: disable=line-too-long

import argparse
from typing import Iterable

import drgn
import sdb
from sdb.commands.internal.util import get_valid_struct_name


class ContainerOf(sdb.Command):
    """
    Get the containing object of a pointer object.

    EXAMPLES
        Trivial example of getting a structure's address
        out of the address of one of its members:

            sdb> addr init_task | cast void *
            (void *)0xffffffffa8217740
            sdb> addr init_task | member comm | addr | container_of struct task_struct comm  | cast void *
            (void *)0xffffffffa8217740

    """

    names = ["container_of"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("struct_name",
                            help="name of struct type to be used")
        parser.add_argument("member", help="name of member within the struct")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        sname = get_valid_struct_name(self, self.args.struct_name)
        for obj in objs:
            try:
                container_obj = drgn.container_of(obj, sname, self.args.member)
            except (TypeError, LookupError) as err:
                raise sdb.CommandError(self.name, str(err))
            yield container_obj
