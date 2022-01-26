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

from typing import Iterable
import os
import drgn
from drgn.helpers.linux.fs import inode_path
import sdb
from sdb.target import type_canonicalize, get_prog
from sdb.command import Command


class Inode2znode(Command):
    """
    Convert an inode to a znode and display it.

    sdb> echo 0xffff9ca45647f588 | cast struct inode * | itoz
    ADDR                    OBJ UNLINKED    BLKSZ               SIZE    ...
    0xffff9ca45647f398        2        0    29184              28772    ...
    """

    names = ["inode2znode", "i2z", "itoz"]

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        for obj in objs:
            obj_type = type_canonicalize(obj.type_)
            if obj_type.kind != drgn.TypeKind.POINTER:
                raise sdb.CommandError(
                    self.name,
                    f"'{obj.type_.type_name()}' is not a valid pointer type")
            obj = drgn.Object(get_prog(),
                              type=obj.type_.type,
                              address=obj.value_())
            znode = drgn.container_of(obj.address_of_(), 'struct znode',
                                      'z_inode')
            znodes = sdb.execute_pipeline([znode], [Znode()])
            Znode.pretty_print(znode, znodes)


class Znode2inode(Command):
    """
    Convert a znode to an inode and display it.

    sdb> echo 0xffff9ca45647f398 | znode | ztoi
    ADDR                    INO     MODE    LINKS   BLOCKS SB
    0xffff9ca45647f588        2    33184        1        1 0xffff9ca464ae8800

    sdb> znode | znode2inode
    ADDR                    INO     MODE    LINKS   BLOCKS SB
    0xffff9ca456478638        2    16877        2        1 0xffff9ca486819800
    0xffff9ca456478a80       34    16877        2        1 0xffff9ca464ae8800
    0xffff9ca456478ec8       -1    16895        1        0 0xffff9ca464ae8800
    0xffff9ca45647b108        3    33184        1        1 0xffff9ca464ae8800
    0xffff9ca45647b998       -1    16895        1        0 0xffff9ca486819800
    0xffff9ca45647c228        3    16877        2        1 0xffff9ca486819800
    0xffff9ca45647dbd8       34    16877        4        1 0xffff9ca486819800
    0xffff9ca45647e8b0       34    16877        2        1 0xffff9ca464aeb000
    0xffff9ca45647f588        2    33184        1        1 0xffff9ca464ae8800
    0xffff9ca45647f9d0       -1    16895        1        0 0xffff9ca464aeb000
    """

    names = ["znode2inode", "z2i", "ztoi"]

    @staticmethod
    def inode_print(znode: drgn.Object) -> None:
        inode = znode.z_inode
        i = drgn.cast('int', znode.z_id)
        print("{:18} {:>8} {:>8} {:>8} {:>8} {:18}".format(
            hex(inode.address_), int(i), int(inode.i_mode), int(inode.i_nlink),
            int(inode.i_blocks), hex(int(inode.i_sb))))

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        print("{:18} {:>8} {:>8} {:>8} {:>8} {:18}".format(
            "ADDR", "INO", "MODE", "LINKS", "BLOCKS", "SB"))
        for obj in objs:
            obj_type = type_canonicalize(obj.type_)
            if obj_type.kind != drgn.TypeKind.POINTER:
                raise sdb.CommandError(
                    self.name,
                    f"'{obj.type_.type_name()}' is not a valid pointer type")
            obj = drgn.Object(get_prog(),
                              type=obj.type_.type,
                              address=obj.value_())
            self.inode_print(obj)


class Znode(sdb.Locator, sdb.PrettyPrinter):
    """
    Iterate and pretty-print znodes

    DESCRIPTION

    Iterate znodes or convert an address to a znode
    and display it.

    sdb> znode
    ADDR                    OBJ UNLINKED    BLKSZ               SIZE    ...
    0xffff9ca456478448        2        0      512                  2    ...
    0xffff9ca456478890       34        0      512                  6    ...
    0xffff9ca456478cd8       -1        0        0                  0    ...
    0xffff9ca45647af18        3        0    29696              29257    ...
    0xffff9ca45647b7a8       -1        0        0                  0    ...
    0xffff9ca45647c038        3        0      512                  2    ...
    0xffff9ca45647d9e8       34        0      512                  4    ...
    0xffff9ca45647e6c0       34        0      512                  4    ...
    0xffff9ca45647f398        2        0    29184              28772    ...
    0xffff9ca45647f7e0       -1        0        0                  0    ...

    sdb> echo 0xffff9ca45647f398 | znode
    ADDR                    OBJ UNLINKED    BLKSZ               SIZE    ...
    0xffff9ca45647f398        2        0    29184              28772    ...
    """

    names = ["znode"]
    input_type = "znode_t *"
    output_type = "znode_t *"

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        print("{:18} {:>8} {:8} {:>8} {:>18} {:>18} {:>18} {:<18}".format(
            "ADDR", "OBJ", "UNLINKED", "BLKSZ", "SIZE", "INODE", "ZFSVFS", 
            "FILENAME"))
        for znode in objs:
            i = drgn.cast('int', znode.z_id)
            inode = znode.z_inode
            ipath = inode_path(inode)
            fn = ""
            if ipath is not None:
                fn = os.fsdecode(ipath)
            print(
                "{:18} {:>8d} {:>8d} {:>8d} {:>18} {:>18} {:>18} {:<18}".format(
                    hex(znode), int(i), int(znode.z_unlinked),
                    int(znode.z_blksz), int(znode.z_size),
                    hex(znode.z_inode.address_of_()),
                    hex(znode.z_inode.i_sb.s_fs_info), str(fn)))

    def no_input(self) -> drgn.Object:
        znode_cache = drgn.cast("spl_kmem_cache_t *",
                                sdb.get_object("znode_cache"))
        znode_kmem = znode_cache.skc_linux_cache
        znodes = sdb.execute_pipeline(
            [znode_kmem],
            [sdb.Walk(), sdb.Cast(["znode_t *"])],
        )
        for znode in znodes:
            if znode.z_id != 0:
                yield znode
