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
"""This module contains the "sdb.Coerce" class."""

import argparse
from typing import Iterable

import drgn
import sdb


class Coerce(sdb.Command):
    """
    This command massages its input types into different types. This
    usually involves stripping typedevs or qualifiers, adding pointers to
    go from a "struct" to a "struct *", or casting an "int" or "void *"
    to the appropriate pointer type.
    """

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)
        if not self.args.type:
            self.parser.error("the following arguments are required: type")

        self.type = self.prog.type(" ".join(self.args.type))

        if self.type.kind is not drgn.TypeKind.POINTER:
            raise TypeError("can only coerce to pointer types, not {}".format(
                self.type))

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        #
        # We use REMAINDER here to allow the type to be specified
        # without the user having to worry about escaping whitespace.
        # The drawback of this is an error will not be automatically
        # thrown if no type is provided. To workaround this, we check
        # the parsed arguments, and explicitly throw an error if needed.
        #
        parser.add_argument("type", nargs=argparse.REMAINDER)
        self.parser = parser

    def coerce(self, obj: drgn.Object) -> drgn.Object:
        """
        This function attemts to massage the input object into an object
        of a different type.
        """

        # same type is fine
        if obj.type_ == self.type:
            return obj

        # "void *" can be coerced to any pointer type
        if (obj.type_.kind is drgn.TypeKind.POINTER and
                obj.type_.primitive is drgn.PrimitiveType.C_VOID):
            return drgn.cast(self.type, obj)

        # integers can be coerced to any pointer typo
        if obj.type_.kind is drgn.TypeKind.INT:
            return drgn.cast(self.type, obj)

        # "type" can be coerced to "type *"
        if obj.type_.kind is not drgn.TypeKind.POINTER and obj.address_of_(
        ).type_ == self.type:
            return obj.address_of_()

        raise TypeError("can not coerce {} to {}".format(obj.type_, self.type))

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            yield self.coerce(obj)
