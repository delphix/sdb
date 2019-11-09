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

    "Print command usage"

    names = ["help"]

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('-v', '--verbose', action='store_true')
        parser.add_argument('cmd', nargs='?')

    def call(self, objs: Iterable[drgn.Object]):
        if self.args.cmd:
            if self.args.cmd in sdb.all_commands:
                cmd_list = [ self.args.cmd ]
            else:
                print('Unknown command: ' + self.args.cmd)
                return
        else:
            # If command isn't specified, add commands from all_commands
            # to the list. Note that all_commands includes commands and
            # aliases. Filter out the aliases when listing the commands
            cmd_list = []
            aliases = []
            for c in sdb.all_commands:
                if c in aliases:
                    aliases.remove(c)
                else:
                    cmd_list.append(c)
                    # Add names to aliases but remove the current one
                    aliases.extend(sdb.all_commands[c].names)
                    aliases.remove(c)

        for c in cmd_list:
            sdb.all_commands[c].help(c, self.args.verbose)
