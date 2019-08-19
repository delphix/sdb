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


class PyFilter(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["pyfilter"]

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)
        if not self.args.expr:
            self.parser.error("the following arguments are required: expr")

        try:
            self.code = compile(" ".join(self.args.expr), "<string>", "eval")
        except SyntaxError as err:
            raise sdb.CommandEvalSyntaxError(self.name, err)

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("expr", nargs=argparse.REMAINDER)
        self.parser = parser

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        # pylint: disable=eval-used
        func = lambda obj: eval(self.code, {'__builtins__': None}, {'obj': obj})
        try:
            yield from filter(func, objs)
        except (TypeError, AttributeError) as err:
            raise sdb.CommandError(self.name, str(err))
