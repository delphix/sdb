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


def is_hex(arg: str) -> bool:
    try:
        int(arg, 16)
        return True
    except ValueError:
        return False


def resolve_for_address(prog: drgn.Program, arg: str) -> drgn.Object:
    if is_hex(arg):
        return drgn.Object(prog, "void *", value=int(arg, 16))
    return prog[arg].address_of_()


class Address(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["address", "addr"]

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        super()._init_argparse(parser)
        parser.add_argument("symbols", nargs="*", metavar="<symbol>")

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            if obj.address_ is None:
                #
                # This may not be very intuitive. How can we have
                # an object that doesn't have an address? The answer
                # is that this object was created from sdb (most
                # probably through an echo command that is piped
                # to us) and thus doesn't exist in the address space
                # of our target. This is a weird and rare use-case
                # but it keeps things simple for now. If we ever
                # see this causing problems we should definitely
                # rethink this as being the default behavior. An
                # alternative for example could be that we throw
                # an error that the object doesn't exist in the
                # address space of the target.
                #
                yield obj
            else:
                yield obj.address_of_()

        for symbol in self.args.symbols:
            try:
                yield resolve_for_address(self.prog, symbol)
            except KeyError:
                raise sdb.SymbolNotFoundError(self.name, symbol)
