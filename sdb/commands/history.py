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

import readline
import argparse
from typing import Iterable

import drgn
import sdb


class History(sdb.Command):
    """
    Display command history.
    """
    # pylint: disable=too-few-public-methods

    names = ["history"]
    load_on = [sdb.All()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("count", nargs="?", type=int)
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        stop = readline.get_current_history_length() + 1
        if self.args.count is not None:
            start = stop - self.args.count
        else:
            start = 1
        for i in range(start, stop):
            print(f"{i:5}  {readline.get_history_item(i)}")
