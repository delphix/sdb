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

# pylint: disable=missing-docstring

import argparse
from typing import Iterable

import drgn
import sdb


class Cast(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["cast"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        #
        # We use REMAINDER here to allow the type to be specified
        # without the user having to worry about escaping whitespace.
        # The drawback of this is an error will not be automatically
        # thrown if no type is provided. To workaround this, we check
        # the parsed arguments, and explicitly throw an error if needed.
        #
        parser.add_argument("type", nargs=argparse.REMAINDER)
        return parser

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)
        if not self.args.type:
            self.parser.error("the following arguments are required: <type>")

        tname = " ".join(self.args.type)
        try:
            self.type = self.prog.type(tname)
        except LookupError:
            raise sdb.CommandError(self.name, f"could not find type '{tname}'")

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            try:
                yield drgn.cast(self.type, obj)
            except TypeError as err:
                raise sdb.CommandError(self.name, str(err))
