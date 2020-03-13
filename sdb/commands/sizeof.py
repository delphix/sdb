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
import sdb
from sdb.commands.internal import util


class SizeOf(sdb.Command):
    """
    Print the size of a type in bytes.

    DESCRIPTION
       The type can be specified by name as an argument, or
       by object through a pipe.

    EXAMPLES
        Print the size of struct task_struct and spa_t:

            sdb> sizeof task_struct spa_t
            (size_t)9152
            (size_t)9176

        Figuring out the size of objects passed through a
        pipe:

            sdb> addr spa_namespace_avl | deref | sizeof
            (size_t)40
    """

    names = ["sizeof"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("type", nargs="*", metavar="<type>")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for tname in self.args.type:
            type_ = util.get_valid_type_by_name(self, tname)
            yield sdb.create_object('size_t', sdb.type_canonicalize_size(type_))
        for obj in objs:
            yield sdb.create_object('size_t',
                                    sdb.type_canonicalize_size(obj.type_))
