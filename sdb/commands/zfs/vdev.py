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
from typing import Iterable, List, Tuple, Optional

import drgn
import sdb
from sdb.commands.zfs.internal import enum_lookup
from sdb.commands.zfs.metaslab import Metaslab
from sdb.commands.zfs.histograms import ZFSHistogram


class Vdev(sdb.Locator, sdb.PrettyPrinter):
    names = ["vdev"]
    input_type = "vdev_t *"
    output_type = "vdev_t *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
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
        return parser

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.arg_list: List[str] = []
        if self.args.histogram:
            self.arg_list.append("-H")
        if self.args.weight:
            self.arg_list.append("-w")

    #
    # Iterate over the metaslabs to accumulate histogram data.
    #
    @staticmethod
    def sum_histograms(
            metaslabs: Iterable[drgn.Object]) -> Tuple[drgn.Object, int]:
        shift = -1
        length = 1
        first_time = True
        histsum: List[int] = []
        for msp in metaslabs:
            if msp.ms_sm == sdb.get_typed_null(msp.ms_sm.type_):
                continue
            histogram = msp.ms_sm.sm_phys.smp_histogram
            if first_time:
                shift = int(msp.ms_sm.sm_shift)
                length = len(histogram)
                histsum = [0] * length
            assert length == len(histogram)
            assert shift == int(msp.ms_sm.sm_shift)
            for (bucket, value) in enumerate(histogram):
                histsum[bucket] += int(value)
            first_time = False
        return sdb.create_object(f'uint64_t[{length}]', histsum), shift

    def pretty_print(self,
                     vdevs: Iterable[drgn.Object],
                     indent: int = 0) -> None:
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
                    enum_lookup("vdev_state_t", vdev.vdev_state).ljust(7),
                    enum_lookup("vdev_aux_t", vdev.vdev_stat.vs_aux).ljust(4),
                    "".ljust(level),
                    vdev.vdev_path.string_().decode("utf-8"),
                )

            else:
                print(
                    "".ljust(indent),
                    hex(vdev).ljust(18),
                    enum_lookup("vdev_state_t", vdev.vdev_state).ljust(7),
                    enum_lookup("vdev_aux_t", vdev.vdev_stat.vs_aux).ljust(4),
                    "".ljust(level),
                    vdev.vdev_ops.vdev_op_type.string_().decode("utf-8"),
                )
            if self.args.histogram:
                metaslabs = sdb.execute_pipeline([vdev], [Metaslab()])
                histsum, shift = self.sum_histograms(metaslabs)
                if shift > 0:
                    ZFSHistogram.print_histogram(histsum, shift, indent + 5)

            if self.args.metaslab:
                metaslabs = sdb.execute_pipeline([vdev], [Metaslab()])
                Metaslab(self.arg_list).pretty_print(metaslabs, indent + 5)

    @sdb.InputHandler("spa_t*")
    def from_spa(self, spa: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.vdev_ids:
            # yield the requested top-level vdevs
            for i in self.args.vdev_ids:
                if i >= spa.spa_root_vdev.vdev_children:
                    raise sdb.CommandError(
                        self.name,
                        "vdev id {} not valid; there are only {} vdevs in {}".
                        format(i, int(spa.spa_root_vdev.vdev_children),
                               spa.spa_name.string_().decode("utf-8")))
                yield spa.spa_root_vdev.vdev_child[i]
        else:
            yield from self.from_vdev(spa.spa_root_vdev)

    @sdb.InputHandler("vdev_t*")
    def from_vdev(self, vdev: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.vdev_ids:
            raise sdb.CommandError(
                self.name, "when providing a vdev, "
                "specific child vdevs can not be requested")
        yield vdev
        for cid in range(int(vdev.vdev_children)):
            cvd = vdev.vdev_child[cid]
            yield from self.from_vdev(cvd)
