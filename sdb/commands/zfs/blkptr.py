#
# Copyright 2019, 2023 Delphix
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

import drgn
import sdb
from sdb.commands.zfs.internal import (
    BP_GET_TYPE, BP_GET_CHECKSUM, BP_GET_COMPRESS, BP_GET_LEVEL, BP_GET_LSIZE,
    BP_GET_BIRTH, BP_GET_PSIZE, BP_LOGICAL_BIRTH, BP_IS_HOLE, BP_GET_NDVAS,
    BP_IS_ENCRYPTED, BP_IS_GANG, BP_GET_LAYER, BP_IS_AUTHENTICATED,
    BP_HAS_INDIRECT_MAC_CKSUM, BP_GET_BYTEORDER, BP_GET_DEDUP, BP_IS_EMBEDDED,
    BP_IS_REDACTED, BP_GET_FILL, BP_GET_IV2, DVA_IS_VALID, DVA_GET_VDEV,
    DVA_GET_OFFSET, DVA_GET_ASIZE, BPE_GET_ETYPE)


class Blkptr(sdb.PrettyPrinter):
    """
    DESCRIPTION

        Pretty-print zfs block pointers.

    EXAMPLES

        sdb> dbuf | head 1 | member db_blkptr | blkptr
        DVA[0]=<0:2cefd5e00:20000> [L0 ZFS plain file] fletcher4 uncompressed unencrypted LE
        contiguous unique single 20000L/20000P birth=1624L/1624P fill=1 cksum=3feb86d3fa14:
        ff98411222361a1:7cd8eb3816d141e1:2d65ae38a67197c7

        sdb> echo 0xffffa0889343c680 | blkptr
        DVA[0]=<0:41e90000:30000> [L0 ZFS plain file] fletcher4 uncompressed unencrypted LE
        contiguous unique single 20000L/20000P birth=10L/10P fill=1 cksum=3ffba121eb4d:
        ffd4345f8d679e2:efa124922f72ec66:34642a9a05fbafef
    """

    names = ["blkptr"]
    input_type = "blkptr_t *"
    load_on = [sdb.Module("zfs"), sdb.Library("libzpool")]

    def get_ot_name(self, bp: drgn.Object) -> str:
        return str(
            sdb.get_object("dmu_ot")[BP_GET_TYPE(bp)].ot_name.string_().decode(
                "utf-8"))

    def get_checksum(self, bp: drgn.Object) -> str:
        checksum = sdb.get_object("zio_checksum_table")[BP_GET_CHECKSUM(
            bp)].ci_name
        return str(checksum.string_().decode("utf-8"))

    def get_compress(self, bp: drgn.Object) -> str:
        compress = sdb.get_object("zio_compress_table")[BP_GET_COMPRESS(
            bp)].ci_name
        return str(compress.string_().decode("utf-8"))

    def print_hole(self, bp: drgn.Object) -> None:
        print(f"HOLE [L{BP_GET_LEVEL(bp)} {self.get_ot_name(bp)}]", end=' ')
        print(f"size={BP_GET_LSIZE(bp):#x}L birth={BP_GET_BIRTH(bp):#x}L")

    def print_embedded(self, bp: drgn.Object) -> None:
        print(f"EMBEDDED [L{BP_GET_LEVEL(bp)}", end=' ')
        print(f"{self.get_ot_name(bp)}]", end=' ')
        print(f"et={BPE_GET_ETYPE(bp)} {BP_GET_COMPRESS(bp)} ", end=' ')
        print(f"size={BP_GET_LSIZE(bp):#x}L/{BP_GET_PSIZE(bp):#x}P ", end=' ')
        print(f"birth={BP_LOGICAL_BIRTH(bp)}L")

    def print_redacted(self, bp: drgn.Object) -> None:
        print(f"REDACTED [L{BP_GET_LEVEL(bp)}", end=' ')
        print(f"{self.get_ot_name(bp)}] size={BP_GET_LSIZE(bp):#x}", end=' ')
        print(f"birth={BP_LOGICAL_BIRTH(bp):#x}")

    def get_byteorder(self, bp: drgn.Object) -> str:
        if BP_GET_BYTEORDER(bp) == 0:
            return "BE"
        return "LE"

    def get_gang(self, bp: drgn.Object) -> str:
        if BP_IS_GANG(bp):
            return "gang"
        return "contiguous"

    def get_dedup(self, bp: drgn.Object) -> str:
        if BP_GET_DEDUP(bp):
            return "dedup"
        return "unique"

    def get_crypt(self, bp: drgn.Object) -> str:
        if BP_IS_ENCRYPTED(bp):
            return "encrypted"
        if BP_IS_AUTHENTICATED(bp):
            return "authenticated"
        if BP_HAS_INDIRECT_MAC_CKSUM(bp):
            return "indirect-MAC"
        return "unencrypted"

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        copyname = ['zero', 'single', 'double', 'triple']
        copies = 0

        for bp in objs:
            if bp is None:
                print("<NULL>")
                continue

            if BP_IS_HOLE(bp):
                self.print_hole(bp)
            elif BP_IS_EMBEDDED(bp):
                self.print_embedded(bp)
            elif BP_IS_REDACTED(bp):
                self.print_redacted(bp)
            else:

                for d in range(0, BP_GET_NDVAS(bp)):
                    if DVA_IS_VALID(bp.blk_dva[d]):
                        copies += 1
                    print(f"DVA[{d}]=<{DVA_GET_VDEV(bp.blk_dva[d])}:", end='')
                    print(f"{DVA_GET_OFFSET(bp.blk_dva[d]):#x}:", end='')
                    print(f"{DVA_GET_ASIZE(bp.blk_dva[d]):#x}>")

                if BP_IS_ENCRYPTED(bp):
                    print(f"salt={bp.blk_dva[2].dva_word[0]:#x}", end=' ')
                    print(f"iv={bp.blk_dva[2].dva_word[1]:#x}", end='')
                    print(f"{BP_GET_IV2(bp):#x}")

                if BP_IS_GANG(bp) and (DVA_GET_ASIZE(bp.blk_dva[2]) <=
                                       DVA_GET_ASIZE(bp.blk_dva[1]) / 2):
                    copies -= 1

                print(f"[L{BP_GET_LEVEL(bp)}", end=' ')
                print(f"{self.get_ot_name(bp)}]", end=' ')
                print(f"{self.get_checksum(bp)}", end=' ')
                print(f"{self.get_compress(bp)}", end=' ')

                print(f"layer={BP_GET_LAYER(bp)}", end=' ')
                print(f"{self.get_crypt(bp)}", end=' ')
                print(f"{self.get_byteorder(bp)}", end=' ')
                print(f"{self.get_gang(bp)} {self.get_dedup(bp)}", end=' ')
                print(f"{copyname[copies]}")

                print(f"size={BP_GET_LSIZE(bp):#x}L/{BP_GET_PSIZE(bp):#x}P",
                      end=' ')
                print(f"birth={BP_LOGICAL_BIRTH(bp)}L", end='/')
                print(f"{BP_GET_BIRTH(bp)}P", end=' ')
                print(f"fill={int(BP_GET_FILL(bp))}")

                print(f"cksum={int(bp.blk_cksum.zc_word[0]):#x}", end='')
                print(f":{int(bp.blk_cksum.zc_word[1]):#x}", end='')
                print(f":{int(bp.blk_cksum.zc_word[2]):#x}", end='')
                print(f":{int(bp.blk_cksum.zc_word[3]):#x}")
