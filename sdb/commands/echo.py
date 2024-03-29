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


class Echo(sdb.Command):
    """
    Creates an object of type (void *) from the given address or addresses
    """

    names = ["echo", "cc"]
    load_on = [sdb.All()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("addrs", nargs="*", metavar="<address>")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            yield obj

        for addr in self.args.addrs:
            try:
                value_ = int(addr, 0)
            except ValueError as err:
                raise sdb.CommandInvalidInputError(self.name, addr) from err
            yield sdb.create_object("void *", value_)
