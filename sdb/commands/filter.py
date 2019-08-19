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


class Filter(sdb.Command):
    # pylint: disable=too-few-public-methods
    # pylint: disable=eval-used

    names = ["filter"]

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)
        if not self.args.expr:
            self.parser.error("the following arguments are required: expr")

        index = None
        operators = ["==", "!=", ">", "<", ">=", "<="]
        for operator in operators:
            try:
                index = self.args.expr.index(operator)
                # Use the first comparison operator we find.
                break
            except ValueError:
                continue

        if index is None:
            # If the comparison index is still None, this means not
            # operator was found. This is an error.
            raise sdb.CommandInvalidInputError(
                self.name, "comparison operator is missing")

        if index == 0:
            # If the comparison index is found to be 0, this means
            # there's no left hand side of the comparison to compare the
            # right hand side to. This is an error.
            raise sdb.CommandInvalidInputError(
                self.name, "left hand side of expression is missing")

        if index == len(self.args.expr) - 1:
            # If the index is found to be at the very end of the list,
            # this means there's no right hand side of the comparison to
            # compare the left hand side to. This is an error.
            raise sdb.CommandInvalidInputError(
                self.name, "right hand side of expression is missing")

        try:
            self.lhs_code = compile(" ".join(self.args.expr[:index]),
                                    "<string>", "eval")
            self.rhs_code = compile(" ".join(self.args.expr[index + 1:]),
                                    "<string>", "eval")
        except SyntaxError as err:
            raise sdb.CommandEvalSyntaxError(self.name, err)

        self.compare = self.args.expr[index]

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("expr", nargs=argparse.REMAINDER)
        self.parser = parser

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        try:
            for obj in objs:
                lhs = eval(self.lhs_code, {'__builtins__': None}, {'obj': obj})
                rhs = eval(self.rhs_code, {'__builtins__': None}, {'obj': obj})

                if not isinstance(lhs, drgn.Object):
                    raise sdb.CommandInvalidInputError(
                        self.name,
                        "left hand side has unsupported type ({})".format(
                            type(lhs).__name__))

                if isinstance(rhs, str):
                    lhs = lhs.string_().decode("utf-8")
                elif isinstance(rhs, int):
                    rhs = drgn.Object(self.prog, type=lhs.type_, value=rhs)
                elif isinstance(rhs, bool):
                    pass
                elif isinstance(rhs, drgn.Object):
                    pass
                else:
                    raise sdb.CommandInvalidInputError(
                        self.name,
                        "right hand side has unsupported type ({})".format(
                            type(rhs).__name__))

                if eval("lhs {} rhs".format(self.compare),
                        {'__builtins__': None}, {
                            'lhs': lhs,
                            'rhs': rhs
                        }):
                    yield obj
        except (AttributeError, TypeError, ValueError) as err:
            raise sdb.CommandError(self.name, str(err))
