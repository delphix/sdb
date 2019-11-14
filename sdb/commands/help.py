#
# Copyright 2019 Chuck Tuffli
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


class Help(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["help"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super(Help, cls)._init_parser(name)
        parser.add_argument("cmd", type=str)
        return parser

    def call(self, objs: Iterable[drgn.Object]) -> None:
        try:
            sdb.all_commands[self.args.cmd].help(self.args.cmd)
        except KeyError:
            raise sdb.error.CommandNotFoundError(self.args.cmd)
