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
from sdb.commands.zfs.internal import enum_lookup
from sdb.commands.zfs.metaslab import Metaslab


class Vdev(sdb.Locator, sdb.PrettyPrinter):
    names = ["vdev"]
    input_type = "vdev_t *"
    output_type = "vdev_t *"

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)
        self.arg_string = ""
        if self.args.histogram:
            self.arg_string += "-H "
        if self.args.weight:
            self.arg_string += "-w "

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-m",
            "--metaslab",
            action="store_true",
            default=False,
            help="metaslab flag",
        )

        parser.add_argument(
            "-H",
            "--histogram",
            action="store_true",
            default=False,
            help="histogram flag",
        )

        parser.add_argument("-w",
                            "--weight",
                            action="store_true",
                            default=False,
                            help="weight flag")

        parser.add_argument("vdev_ids", nargs="*", type=int)

    def pretty_print(self, vdevs, indent=0):
        print(
            "".ljust(indent),
            "ADDR".ljust(18),
            "STATE".ljust(7),
            "AUX".ljust(4),
            "DESCRIPTION",
        )
        print("".ljust(indent), "-" * 60)

        for vdev in vdevs:
            level = 0
            pvd = vdev.vdev_parent
            while pvd:
                level += 2
                pvd = pvd.vdev_parent

            if int(vdev.vdev_path) != 0:
                print(
                    "".ljust(indent),
                    hex(vdev).ljust(18),
                    enum_lookup(self.prog, "vdev_state_t",
                                vdev.vdev_state).ljust(7),
                    enum_lookup(self.prog, "vdev_aux_t",
                                vdev.vdev_stat.vs_aux).ljust(4),
                    "".ljust(level),
                    vdev.vdev_path.string_().decode("utf-8"),
                )

            else:
                print(
                    "".ljust(indent),
                    hex(vdev).ljust(18),
                    enum_lookup(self.prog, "vdev_state_t",
                                vdev.vdev_state).ljust(7),
                    enum_lookup(self.prog, "vdev_aux_t",
                                vdev.vdev_stat.vs_aux).ljust(4),
                    "".ljust(level),
                    vdev.vdev_ops.vdev_op_type.string_().decode("utf-8"),
                )
            if self.args.metaslab:
                metaslabs = sdb.execute_pipeline(self.prog, [vdev],
                                                 [Metaslab(self.prog)])
                Metaslab(self.prog,
                         self.arg_string).pretty_print(metaslabs, indent + 5)

    @sdb.InputHandler("spa_t*")
    def from_spa(self, spa: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.vdev_ids:
            # yield the requested top-level vdevs
            for i in self.args.vdev_ids:
                if i >= spa.spa_root_vdev.vdev_children:
                    raise TypeError(
                        "vdev id {} not valid; there are only {} vdevs in {}".
                        format(
                            i,
                            spa.spa_root_vdev.vdev_children,
                            spa.spa_name.string_().decode("utf-8"),
                        ))
                yield spa.spa_root_vdev.vdev_child[i]
        else:
            yield from self.from_vdev(spa.spa_root_vdev)

    @sdb.InputHandler("vdev_t*")
    def from_vdev(self, vdev: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.vdev_ids:
            raise TypeError(
                "when providing a vdev, specific child vdevs can not be requested"
            )
        yield vdev
        for cid in range(0, int(vdev.vdev_children)):
            cvd = vdev.vdev_child[cid]
            yield from self.from_vdev(cvd)
