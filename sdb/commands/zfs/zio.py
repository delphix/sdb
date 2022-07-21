#
# Copyright 2019 Delphix
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

from typing import Iterable, List, Optional
import os
import drgn
import sdb
from sdb.commands.zfs.internal import enum_lookup, gethrtime, NANOSEC, MSEC


class Zio(sdb.Locator, sdb.PrettyPrinter):
    """
    Iterate and pretty-print zios

    DESCRIPTION

    Iterate zios or convert an address to a zio
    and display it.

    EXAMPLES

    sdb> zio
    ADDR                  TYPE           STAGE            WAITER                 TIME_ELAPSED
    0xffff927ed80d84e0    TYPE_NULL      OPEN
    0xffff927edde6e220    TYPE_NULL      OPEN
    0xffff927edde73a80    TYPE_NULL      CHECKSUM_VERIFY  0xffff927f02dc8000
     0xffff927edde730c0   TYPE_WRITE     VDEV_IO_START
      0xffff927ed8169860  TYPE_WRITE     VDEV_IO_START                           4617ms
      0xffff927ed816a220  TYPE_WRITE     VDEV_IO_START                           4619ms
      0xffff927edde70ea0  TYPE_WRITE     VDEV_IO_START
       0xffff927ed81684e0 TYPE_WRITE     VDEV_IO_START                           4624ms
       0xffff927ed8169d40 TYPE_WRITE     VDEV_IO_START                           4625ms

    sdb> echo 0xffff927ee3439860 | zio
    ADDR                  TYPE           STAGE            WAITER                 TIME_ELAPSED
     0xffff927ee343a700   TYPE_WRITE     VDEV_IO_START                           5487ms

    """

    names = ["zio"]
    input_type = "zio_t *"
    output_type = "zio_t *"

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.level = 0
        self.header = 0

    @staticmethod
    def lookup_stage(enum_type_name: str, value: int) -> str:
        type_ = sdb.type_canonicalize(sdb.get_type(enum_type_name))
        fields = type_.enumerators
        enum_string = ""
        for f in fields:
            if f.value == value:
                enum_string = f.name
                break
        prefix = os.path.commonprefix([f[0] for f in fields])
        return enum_string[prefix.rfind("_") + 1:]

    def print_header(self) -> None:
        print("{:26} {:<14} {:<16} {:<22} {:<8}".format("ADDR", "TYPE", "STAGE",
                                                        "WAITER",
                                                        "TIME_ELAPSED"))
        self.header = 1

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        if self.header == 0:
            self.print_header()
        for zio in objs:
            stage = self.lookup_stage('enum zio_stage', zio.io_stage)
            if stage == "DONE":
                continue
            addr = '%s%s' % (' ' * self.level, format(hex(zio)))
            waiter = "" if sdb.is_null(zio.io_waiter) else hex(
                int(zio.io_waiter))
            now = gethrtime()
            delta_ms = (now - zio.io_timestamp) / (NANOSEC / MSEC)
            delta = str(int(delta_ms)) + 'ms' if zio.io_timestamp != 0 else ""

            print("{:26} {:<14} {:<16} {:<22} {:<8}".format(
                addr,
                enum_lookup("zio_type_t", zio.io_type).ljust(14),
                stage.ljust(8), waiter.ljust(8), delta.ljust(8)))

    @sdb.InputHandler("zio_t*")
    def from_zio(self, zio: drgn.Object) -> Iterable[drgn.Object]:
        yield zio
        child_links = sdb.execute_pipeline(
            [zio.io_child_list.address_of_()],
            [sdb.Walk(), sdb.Cast(["zio_link_t *"])],
        )
        self.level += 1
        for c in child_links:
            cio = c.zl_child
            if cio.io_child_count == 0:
                yield cio
            else:
                yield from self.from_zio(cio)
        self.level -= 1

    def no_input(self) -> drgn.Object:
        zio_cache = drgn.cast("spl_kmem_cache_t *", sdb.get_object("zio_cache"))
        zio_kmem = zio_cache.skc_linux_cache
        zios = sdb.execute_pipeline(
            [zio_kmem],
            [sdb.Walk(), sdb.Cast(["zio_t *"])],
        )
        if self.header == 0:
            self.print_header()
        for zio in zios:
            if zio.io_parent_count == 0:
                if zio.io_child_count == 0:
                    yield zio
                else:
                    yield from self.from_zio(zio)
