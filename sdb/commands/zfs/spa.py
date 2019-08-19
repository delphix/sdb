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

import drgn
import sdb
from sdb.commands.cast import Cast
from sdb.commands.zfs.avl import Avl
from sdb.commands.zfs.vdev import Vdev


class Spa(sdb.Locator, sdb.PrettyPrinter):
    names = ["spa"]
    input_type = "spa_t *"
    output_type = "spa_t *"

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)
        self.arg_string = ""
        if self.args.metaslab:
            self.arg_string += "-m "
        if self.args.histogram:
            self.arg_string += "-H "
        if self.args.weight:
            self.arg_string += "-w "

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-v",
                            "--vdevs",
                            action="store_true",
                            help="vdevs flag")
        parser.add_argument("-m",
                            "--metaslab",
                            action="store_true",
                            help="metaslab flag")
        parser.add_argument("-H",
                            "--histogram",
                            action="store_true",
                            help="histogram flag")
        parser.add_argument("-w",
                            "--weight",
                            action="store_true",
                            help="weight flag")
        parser.add_argument("poolnames", nargs="*")

    def pretty_print(self, spas):
        print("{:14} {}".format("ADDR", "NAME"))
        print("%s" % ("-" * 60))
        for spa in spas:
            print("{:14} {}".format(hex(spa),
                                    spa.spa_name.string_().decode("utf-8")))
            if self.args.vdevs:
                vdevs = sdb.execute_pipeline(self.prog, [spa],
                                             [Vdev(self.prog)])
                Vdev(self.prog, self.arg_string).pretty_print(vdevs, 5)

    def no_input(self):
        spas = sdb.execute_pipeline(
            self.prog,
            [self.prog["spa_namespace_avl"].address_of_()],
            [Avl(self.prog), Cast(self.prog, "spa_t *")],
        )
        for spa in spas:
            if (self.args.poolnames and
                    spa.spa_name.string_() not in self.args.poolnames):
                continue
            yield spa
