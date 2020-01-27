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
from typing import Iterable, Dict, Type

import drgn
import sdb


class Help(sdb.Command):
    """ Displays help for the specified command for ex: help addr """

    names = ["help", "man"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("cmd", nargs="?", type=str)
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        all_cmds = sdb.get_registered_commands()
        if self.args.cmd is not None:
            try:
                all_cmds[self.args.cmd].help(self.args.cmd)
            except KeyError:
                raise sdb.error.CommandNotFoundError(self.args.cmd)
        else:
            cmds: Dict[str, Type[sdb.Command]] = {}
            for k, v in all_cmds.items():
                if v not in cmds.values():
                    cmds[k] = v
            for k in sorted(cmds):
                names = cmds[k].names
                hs = cmds[k].__doc__
                if hs is not None:
                    h = hs.split('\n', 2)
                    hlp = h[0] if h[0] else h[1]
                    if h:
                        print(f"{','.join(names) :32} - {hlp.lstrip()}")
                    else:
                        print(f"{','.join(names) :32}")
                else:
                    print(f"{','.join(names) :32}")
