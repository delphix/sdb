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
import datetime
from typing import Iterable

import drgn
import sdb
from sdb.commands.spl.spl_list import SPLList


class ZfsDbgmsg(sdb.Locator, sdb.PrettyPrinter):
    names = ["zfs_dbgmsg"]
    input_type = "zfs_dbgmsg_t *"
    output_type = "zfs_dbgmsg_t *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument('--verbose', '-v', action='count', default=0)
        return parser

    # obj is a zfs_dbgmsg_t*
    @staticmethod
    def print_msg(obj: drgn.Object,
                  timestamp: bool = False,
                  addr: bool = False) -> None:
        if addr:
            print("{} ".format(hex(obj)), end="")  # type: ignore
        if timestamp:
            timestamp = datetime.datetime.fromtimestamp(int(obj.zdm_timestamp))
            print("{}: ".format(timestamp.strftime("%Y-%m-%dT%H:%M:%S")),
                  end="")

        print(drgn.cast("char *", obj.zdm_msg).string_().decode("utf-8"))

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        for obj in objs:
            ZfsDbgmsg.print_msg(obj, self.args.verbose >= 1,
                                self.args.verbose >= 2)

    def no_input(self) -> Iterable[drgn.Object]:
        proc_list = sdb.get_object("zfs_dbgmsgs").pl_list
        list_addr = proc_list.address_of_()

        yield from sdb.execute_pipeline(
            [list_addr], [SPLList(), sdb.Cast("zfs_dbgmsg_t *")])
