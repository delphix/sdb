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
from typing import Iterable, List, Optional

import drgn
import sdb


class Filter(sdb.SingleInputCommand):
    """
    Return objects matching expression

    EXAMPLES
        Print addresses greater than or equal to 4

            sdb> addr 0 1 2 3 4 5 6 | filter "obj >= 4"
            (void *)0x4
            (void *)0x5
            (void *)0x6

        Find the SPA object of the ZFS pool named "jax" and print its 'spa_name'

            sdb> spa | filter 'obj.spa_name == "jax"' | member spa_name
            (char [256])"jax"

        Print the number of level 3 log statements in the kernel log buffer

            sdb> dmesg | filter 'obj.level == 3' | count
            (unsigned long long)24
    """
    # pylint: disable=eval-used

    names = ["filter"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("expr", nargs=1)
        return parser

    @staticmethod
    def _parse_expression(input_expr: str) -> List[str]:
        pass

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.expr = self.args.expr[0].split()

        index = None
        operators = ["==", "!=", ">", "<", ">=", "<="]
        for operator in operators:
            try:
                index = self.expr.index(operator)
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

        if index == len(self.expr) - 1:
            # If the index is found to be at the very end of the list,
            # this means there's no right hand side of the comparison to
            # compare the left hand side to. This is an error.
            raise sdb.CommandInvalidInputError(
                self.name, "right hand side of expression is missing")

        try:
            self.lhs_code = compile(" ".join(self.expr[:index]), "<string>",
                                    "eval")
            self.rhs_code = compile(" ".join(self.expr[index + 1:]), "<string>",
                                    "eval")
        except SyntaxError as err:
            raise sdb.CommandEvalSyntaxError(self.name, err)

        self.compare = self.expr[index]

    def _call_one(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        try:
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
                rhs = sdb.create_object(lhs.type_, rhs)
            elif isinstance(rhs, bool):
                pass
            elif isinstance(rhs, drgn.Object):
                pass
            else:
                raise sdb.CommandInvalidInputError(
                    self.name,
                    "right hand side has unsupported type ({})".format(
                        type(rhs).__name__))

            if eval("lhs {} rhs".format(self.compare), {'__builtins__': None}, {
                    'lhs': lhs,
                    'rhs': rhs
            }):
                yield obj
        except (AttributeError, TypeError, ValueError) as err:
            raise sdb.CommandError(self.name, str(err))
