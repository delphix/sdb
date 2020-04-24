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
from sdb.commands.zfs.internal import (
    METASLAB_ACTIVE_MASK, METASLAB_WEIGHT_CLAIM, METASLAB_WEIGHT_PRIMARY,
    METASLAB_WEIGHT_SECONDARY, METASLAB_WEIGHT_TYPE, WEIGHT_GET_COUNT,
    WEIGHT_GET_INDEX, WEIGHT_IS_SPACEBASED, BTREE_LEAF_SIZE, nicenum)
from sdb.commands.zfs.histograms import ZFSHistogram


class Metaslab(sdb.Locator, sdb.PrettyPrinter):
    names = ["metaslab"]
    input_type = "metaslab_t *"
    output_type = "metaslab_t *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
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

        parser.add_argument("metaslab_ids", nargs="*", type=int)
        return parser

    @staticmethod
    def metaslab_weight_print(msp: drgn.Object, print_header: bool,
                              indent: int) -> None:
        if print_header:
            print(
                "".ljust(indent),
                "ID".rjust(3),
                "ACTIVE".ljust(6),
                "ALGORITHM".rjust(9),
                "FRAG".rjust(4),
                "ALLOC".rjust(10),
                "MAXSZ".rjust(12),
                "WEIGHT".rjust(12),
            )
            print("".ljust(indent), "-" * 65)
        weight = int(msp.ms_weight)
        if weight & METASLAB_WEIGHT_PRIMARY:
            weight_char = "P"
        elif weight & METASLAB_WEIGHT_SECONDARY:
            weight_char = "S"
        elif weight & METASLAB_WEIGHT_CLAIM:
            weight_char = "C"
        else:
            weight_char = "-"

        if WEIGHT_IS_SPACEBASED(weight):
            algorithm = "SPACE"
        else:
            algorithm = "SEGMENT"

        print(
            "".ljust(indent),
            str(int(msp.ms_id)).rjust(3),
            weight_char.rjust(4),
            "L" if msp.ms_loaded else " ",
            algorithm.rjust(8),
            end="",
        )
        if msp.ms_fragmentation == -1:
            print("-".rjust(6), end="")
        else:
            print((str(msp.ms_fragmentation) + "%").rjust(5), end="")
        print(
            str(str(int(msp.ms_allocated_space) >> 20) + "M").rjust(7),
            ("({0:.1f}%)".format(
                int(msp.ms_allocated_space) * 100 / int(msp.ms_size)).rjust(7)),
            nicenum(msp.ms_max_size).rjust(10),
            end="",
        )

        if WEIGHT_IS_SPACEBASED(weight):
            print(
                "",
                nicenum(weight &
                        ~(METASLAB_ACTIVE_MASK | METASLAB_WEIGHT_TYPE)).rjust(
                            12),
            )
        else:
            count = str(WEIGHT_GET_COUNT(weight))
            size = nicenum(1 << WEIGHT_GET_INDEX(weight))
            print("", (count + " x " + size).rjust(12))

    @staticmethod
    def print_metaslab(msp: drgn.Object, print_header: bool,
                       indent: int) -> None:
        spacemap = msp.ms_sm

        if print_header:
            print(
                "".ljust(indent),
                "ADDR".ljust(18),
                "ID".rjust(4),
                "OFFSET".rjust(16),
                "FREE".rjust(8),
                "FRAG".rjust(5),
                "UCMU".rjust(8),
            )
            print("".ljust(indent), "-" * 65)

        free = msp.ms_size
        if spacemap != sdb.get_typed_null(spacemap.type_):
            free -= spacemap.sm_phys.smp_alloc

        ufrees = msp.ms_unflushed_frees.rt_space
        uallocs = msp.ms_unflushed_allocs.rt_space
        free = free + ufrees - uallocs

        uchanges_free_mem = msp.ms_unflushed_frees.rt_root.bt_num_nodes
        uchanges_free_mem *= BTREE_LEAF_SIZE
        uchanges_alloc_mem = msp.ms_unflushed_allocs.rt_root.bt_num_nodes
        uchanges_alloc_mem *= BTREE_LEAF_SIZE
        uchanges_mem = uchanges_free_mem + uchanges_alloc_mem

        print(
            "".ljust(indent),
            hex(msp).ljust(16),
            str(int(msp.ms_id)).rjust(4),
            hex(msp.ms_start).rjust(16),
            nicenum(free).rjust(8),
            end="",
        )
        if msp.ms_fragmentation == -1:
            print("-".rjust(6), end="")
        else:
            print((str(int(msp.ms_fragmentation)) + "%").rjust(6), end="")
        print(nicenum(uchanges_mem).rjust(9))

    def pretty_print(self,
                     metaslabs: Iterable[drgn.Object],
                     indent: int = 0) -> None:
        first_time = True
        for msp in metaslabs:
            if not self.args.weight:
                Metaslab.print_metaslab(msp, first_time, indent)
            if self.args.histogram:
                spacemap = msp.ms_sm
                if spacemap != sdb.get_typed_null(spacemap.type_):
                    histogram = spacemap.sm_phys.smp_histogram
                    ZFSHistogram.print_histogram(histogram,
                                                 int(spacemap.sm_shift), indent)
                    ZFSHistogram.print_histogram_median(histogram,
                                                        int(spacemap.sm_shift),
                                                        indent)
            if self.args.weight:
                Metaslab.metaslab_weight_print(msp, first_time, indent)
            first_time = False

    @sdb.InputHandler("vdev_t*")
    def from_vdev(self, vdev: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.metaslab_ids:
            # yield the requested metaslabs
            for i in self.args.metaslab_ids:
                if i >= vdev.vdev_ms_count:
                    raise sdb.CommandError(
                        self.name, "metaslab id {} not valid; "
                        "there are only {} metaslabs in vdev id {}".format(
                            i, int(vdev.vdev_ms_count), int(vdev.vdev_id)))
                yield vdev.vdev_ms[i]
        else:
            for i in range(int(vdev.vdev_ms_count)):
                msp = vdev.vdev_ms[i]
                yield msp
