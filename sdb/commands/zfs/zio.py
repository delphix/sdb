#
# Copyright 2023 Delphix
# Copyright 2021 Datto, Inc.
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
from typing import Iterable, List, Optional

import drgn
import sdb
from sdb.commands.zfs.internal import gethrtime, removeprefix, NANOSEC, MSEC


class Zio(sdb.Locator, sdb.PrettyPrinter):
    """
    Iterate and pretty-print ZIOs

    EXAMPLES
        Print all parent ZIOs on the system following their hierarchy
        of children:

            sdb> zio -r
            ADDRESS                        TYPE  STAGE            WAITER             TIME_ELAPSED
            -------------------------------------------------------------------------------------
            0xffff8f16579cc520             NULL  OPEN             -                             -
            0xffff8f16579cca10             NULL  OPEN             -                             -
            0xffff8f165ae07680             NULL  CHECKSUM_VERIFY  0xffff8f14b2bc0000            -
             0xffff8f165ae02780            READ  VDEV_IO_START    -                             -
              0xffff8f165ae06ca0           READ  VDEV_IO_START    -                         133ms
            0xffff8f165d8fa290             NULL  OPEN             -                             -
            0xffff8f165d8fd8e0             NULL  CHECKSUM_VERIFY  0xffff8f14b2bc3d00            -
            ...

        Follow the parent hierarchy of a specific ZIO:

            sdb> echo 0xffff8f165ae06ca0 | zio -p
            -------------------------------------------------------------------------------------
            ADDRESS                        TYPE  STAGE            WAITER             TIME_ELAPSED
            0xffff8f165ae06ca0             READ  VDEV_IO_START    -                         133ms
             0xffff8f165ae02780            READ  VDEV_IO_START    -                             -
              0xffff8f165ae07680           NULL  CHECKSUM_VERIFY  0xffff8f14b2bc0000            -
    """

    names = ["zio"]
    input_type = "zio_t *"
    output_type = "zio_t *"
    load_on = [sdb.Module("zfs"), sdb.Library("libzpool")]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("-r", "--recursive", action='store_true')
        parser.add_argument("-c", "--children", action='store_true')
        parser.add_argument("-p", "--parents", action='store_true')
        return parser

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.level = 0
        self.header_printed = 0

    def print_header(self) -> None:
        if self.header_printed == 0:
            print(f'\033[4m{"ADDRESS":30} {"TYPE":<5} {"STAGE":<16} ' +
                  f'{"WAITER":<18} {"TIME_ELAPSED":>12}\033[0m')
            self.header_printed = 1

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        self.print_header()
        for zio in objs:
            delta = waiter = "-"
            stage = removeprefix(zio.io_stage.format_(type_name=False),
                                 "ZIO_STAGE_")
            if zio.io_error != 0:
                stage = "FAILED"
            io_type = removeprefix(zio.io_type.format_(type_name=False),
                                   "ZIO_TYPE_")
            addr = f'{" " * self.level}{format(hex(zio))}'
            if not sdb.is_null(zio.io_waiter):
                waiter = hex(int(zio.io_waiter))
            if zio.io_timestamp != 0:
                delta_ms = (gethrtime() - int(zio.io_timestamp)) / (NANOSEC /
                                                                    MSEC)
                delta = f"{str(int(delta_ms))}ms"
            print(
                f"{addr:30} {io_type:<5} {stage:<16} {waiter:<18} {delta:>12}")

    @sdb.InputHandler("zio_t*")
    def from_zio(self, zio: drgn.Object) -> Iterable[drgn.Object]:
        yield zio

        self.level += 1
        if self.args.recursive or self.args.children:
            child_links = sdb.execute_pipeline(
                [zio.io_child_list.address_of_()],
                [sdb.Walk(), sdb.Cast(["zio_link_t *"])],
            )
            for c in child_links:
                yield from self.from_zio(c.zl_child)
        elif self.args.parents:
            child_links = sdb.execute_pipeline(
                [zio.io_parent_list.address_of_()],
                [sdb.Walk(), sdb.Cast(["zio_link_t *"])],
            )
            for c in child_links:
                yield from self.from_zio(c.zl_parent)
        self.level -= 1

    @staticmethod
    def zio_has_parents(zio: drgn.Object) -> bool:
        parent_list = zio.io_parent_list.list_head.address_of_()
        first_parent = parent_list.next
        if parent_list != first_parent:
            return True
        return False

    def no_input(self) -> drgn.Object:
        if self.args.parents:
            raise sdb.CommandInvalidInputError(
                self.name, "command argument -p is not applicable " +
                " when printing all parent ZIOs")

        zio_cache = drgn.cast("spl_kmem_cache_t *", sdb.get_object("zio_cache"))
        zios = sdb.execute_pipeline(
            [zio_cache.skc_linux_cache],
            [sdb.Walk(), sdb.Cast(["zio_t *"])],
        )
        for zio in zios:
            if not self.zio_has_parents(zio):
                yield from self.from_zio(zio)
