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

import drgn
import sdb
from sdb.commands.zfs.internal import BF64_GET, BF64_GET_SB


class BpInfo:
    """
    Store attributes of the block pointer and
    get formatted representations of them.
    """

    # pylint: disable=too-many-instance-attributes

    ndvas = 0
    level = 0
    ot_type = 0
    compress = 0
    birth = 0
    cksum = 0
    byte_order = 0
    gang = 0
    dedup = 0
    copies = ""
    pbirth = 0
    lsize = ""
    psize = ""
    crypt = ""
    c0 = ""
    c1 = ""
    c2 = ""
    c3 = ""

    def set_ndvas(self, nd: int) -> None:
        self.ndvas = nd

    def set_initial_props(self, bp: drgn.Object) -> None:
        self.level = BF64_GET(bp.blk_prop, 56, 5)
        self.ot_type = int(BF64_GET(bp.blk_prop, 48, 8))
        self.compress = BF64_GET(bp.blk_prop, 32, 7)
        self.lsize = format(Blkptr.bp_get_lsize(bp), 'x')
        self.psize = format(Blkptr.bp_get_psize(bp), 'x')
        self.birth = int(bp.blk_birth)
        self.cksum = BF64_GET(bp.blk_prop, 40, 8)
        self.byte_order = BF64_GET(bp.blk_prop, 63, 1)
        self.crypt = Blkptr.bp_get_crypt(bp, self.ot_type, self.level)
        self.gang = (0 if Blkptr.bp_is_embedded(bp) else BF64_GET(
            bp.blk_dva[0].dva_word[1], 63, 1))
        self.dedup = BF64_GET(bp.blk_prop, 62, 1)
        self.copies = Blkptr.copyname[self.ndvas]
        self.pbirth = Blkptr.bp_physical_birth(bp)
        self.c0 = '%x' % bp.blk_cksum.zc_word[0]
        self.c1 = '%x' % bp.blk_cksum.zc_word[1]
        self.c2 = '%x' % bp.blk_cksum.zc_word[2]
        self.c3 = '%x' % bp.blk_cksum.zc_word[3]

    def get_compstr(self) -> str:
        comps = sdb.get_object("zio_compress_table")
        return str(comps[self.compress].ci_name.string_().decode("utf-8"))

    def get_ot_name(self) -> str:
        if self.ot_type & Blkptr.DMU_OT_NEWTYPE:
            if self.ot_type & Blkptr.DMU_OT_BYTESWAP_MASK > 9:
                print(str(self.ot_type & Blkptr.DMU_OT_BYTESWAP_MASK))
                return str(self.ot_type & Blkptr.DMU_OT_BYTESWAP_MASK)
            bswaps = sdb.get_object("dmu_ot_byteswap")
            swap_entry = bswaps[self.ot_type & Blkptr.DMU_OT_BYTESWAP_MASK]
            byte_swap = swap_entry.ob_name.string_().decode("utf-8")
            meta = "metadata" if self.ot_type & Blkptr.DMU_OT_METADATA else "data"
            return "bswap %s %s" % (meta, byte_swap)
        return str(
            sdb.get_object("dmu_ot")[self.ot_type].ot_name.string_().decode(
                "utf-8"))

    def get_fill(self, bp: drgn.Object) -> int:
        if Blkptr.bp_is_encrypted(bp, self.ot_type, self.level):
            return BF64_GET(bp.blk_fill, 0, 32)
        if Blkptr.bp_is_embedded(bp):
            return 1
        return int(bp.blk_fill)

    def get_cksum_string(self) -> str:
        cksums = sdb.get_object("zio_checksum_table")
        return str(cksums[self.cksum].ci_name.string_().decode("utf-8"))

    def get_endian(self) -> str:
        return "BE" if self.byte_order == 0 else "LE"

    def get_gang(self) -> str:
        return "gang" if self.gang else "contiguous"

    def get_dedup(self) -> str:
        return "dedup" if self.dedup else "unique"


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

    BP_EMBEDDED_TYPE_DATA = 0
    BP_EMBEDDED_TYPE_REDACTED = 2

    SPA_MINBLOCKSHIFT = 9
    SPA_MAXBLOCKSHIFT = 24
    SPA_MAXBLOCKSIZE = 1 << SPA_MAXBLOCKSHIFT
    SPA_ASIZEBITS = 24
    SPA_VDEVBITS = 24
    SPA_LSIZEBITS = 16
    SPA_PSIZEBITS = 16

    TRUE = 1
    FALSE = 0

    DMU_OT_NEWTYPE = 128
    DMU_OT_ENCRYPTED = 32
    DMU_OT_METADATA = 0x40
    DMU_OT_BYTESWAP_MASK = 0x1f

    copyname = ['zero', 'single', 'double', 'triple']

    @staticmethod
    def __bp_is_authenticated(bp: drgn.Object, ot: int, level: int) -> int:
        return (Blkptr.bp_uses_crypt(bp) and level > 0 and
                not Blkptr.dmu_ot_is_encrypted(ot))

    @staticmethod
    def __bp_has_indirect_mac_checksum(bp: drgn.Object, level: int) -> int:
        return Blkptr.bp_uses_crypt(bp) and level > 0

    @staticmethod
    def __dmu_ot_is_valid(bp: drgn.Object) -> int:
        ot = BF64_GET(bp.blk_prop, 48, 8)
        if ot & Blkptr.DMU_OT_NEWTYPE:
            return (ot & Blkptr.DMU_OT_BYTESWAP_MASK < len(
                sdb.get_object("dmu_ot_byteswap")))
        return ot < len(sdb.get_object("dmu_ot"))

    @staticmethod
    def dmu_ot_is_encrypted(ot: int) -> int:
        if ot & Blkptr.DMU_OT_NEWTYPE:
            return ot & Blkptr.DMU_OT_ENCRYPTED
        return int(sdb.get_object("dmu_ot")[ot].ot_encrypt)

    @staticmethod
    def bp_is_embedded(bp: drgn.Object) -> int:
        return BF64_GET(bp.blk_prop, 39, 1)

    @staticmethod
    def bp_is_redacted(bp: drgn.Object) -> int:
        return (Blkptr.bp_is_embedded(bp) and BF64_GET(bp.blk_prop, 40, 8)
                == Blkptr.BP_EMBEDDED_TYPE_REDACTED)

    @staticmethod
    def bp_uses_crypt(bp: drgn.Object) -> int:
        return BF64_GET(bp.blk_prop, 61, 1)

    @staticmethod
    def bp_is_encrypted(bp: drgn.Object, ot: int, level: int) -> int:
        return (Blkptr.bp_uses_crypt(bp) and level <= 0 and
                Blkptr.dmu_ot_is_encrypted(ot))

    @staticmethod
    def bp_get_crypt(bp: drgn.Object, ot: int, level: int) -> str:
        if Blkptr.bp_is_encrypted(bp, ot, level):
            return "encrypted"
        if Blkptr.__bp_is_authenticated(bp, ot, level):
            return "authenticated"
        if Blkptr.__bp_has_indirect_mac_checksum(bp, level):
            return "indirect-MAC"
        return "unencrypted"

    @staticmethod
    def dva_is_empty(bp: drgn.Object) -> int:
        return int(bp.blk_dva[0].dva_word[0] == 0 and
                   bp.blk_dva[0].dva_word[1] == 0)

    @staticmethod
    def dva_get_offset(bp: drgn.Object, which_dva: int) -> int:
        return BF64_GET_SB(bp.blk_dva[which_dva].dva_word[1], 0, 63,
                           Blkptr.SPA_MINBLOCKSHIFT, 0)

    @staticmethod
    def dva_get_vdev(bp: drgn.Object, which_dva: int) -> int:
        return BF64_GET(bp.blk_dva[which_dva].dva_word[0], 32,
                        Blkptr.SPA_VDEVBITS)

    @staticmethod
    def __bp_is_hole(bp: drgn.Object) -> int:
        return Blkptr.bp_is_embedded(bp) != Blkptr.TRUE and Blkptr.dva_is_empty(
            bp)

    @staticmethod
    def dva_get_asize(bp: drgn.Object, which_dva: int) -> int:
        if Blkptr.bp_is_embedded(bp):
            return 0
        return BF64_GET_SB(bp.blk_dva[which_dva].dva_word[0], 0,
                           Blkptr.SPA_ASIZEBITS, Blkptr.SPA_MINBLOCKSHIFT, 0)

    @staticmethod
    def bp_get_ndvas(bp: drgn.Object) -> int:
        ndvas = 0
        for x in range(0, 3):
            ndvas += Blkptr.dva_get_asize(bp, x) != 0
        return ndvas

    @staticmethod
    def bpe_get_lsize(bp: drgn.Object) -> int:
        return BF64_GET_SB(bp.blk_prop, 0, 25, 0, 1)

    @staticmethod
    def bp_get_lsize(bp: drgn.Object) -> int:
        if Blkptr.bp_is_embedded(bp):
            if BF64_GET(bp.blk_prop, 40, 8) == Blkptr.BP_EMBEDDED_TYPE_DATA:
                return Blkptr.bpe_get_lsize(bp)
            return 0
        return BF64_GET_SB(bp.blk_prop, 0, Blkptr.SPA_LSIZEBITS,
                           Blkptr.SPA_MINBLOCKSHIFT, 1)

    @staticmethod
    def bp_get_psize(bp: drgn.Object) -> int:
        if Blkptr.bp_is_embedded(bp):
            return 0
        return BF64_GET_SB(bp.blk_prop, 16, Blkptr.SPA_PSIZEBITS,
                           Blkptr.SPA_MINBLOCKSHIFT, 1)

    @staticmethod
    def bp_physical_birth(bp: drgn.Object) -> int:
        if Blkptr.bp_is_embedded(bp):
            phys = 0
        else:
            phys = bp.blk_phys_birth if bp.blk_phys_birth != 0 else bp.blk_birth
        return int(phys)

    @staticmethod
    def bp_get_checksum(bp: drgn.Object) -> int:
        if Blkptr.bp_is_embedded(bp):
            return 2  # ZIO_CHECKSUM_OFF
        return BF64_GET(bp.blk_prop, 40, 8)

    @staticmethod
    def bp_validate(bp: drgn.Object) -> int:
        errors = 0
        addr = hex(bp)
        if not Blkptr.__dmu_ot_is_valid(bp):
            tp = BF64_GET(bp.blk_prop, 48, 8)
            print(f"blkptr at {addr} has invalid TYPE {tp}")
            errors += 1
        ck = Blkptr.bp_get_checksum(bp)
        if ck >= len(sdb.get_object("zio_checksum_table")) or ck <= 1:
            print(f"blkptr at {addr} has invalid CHECKSUM {ck}")
            errors += 1
        comp = BF64_GET(bp.blk_prop, 32, 7)
        if comp >= len(sdb.get_object("zio_compress_table")) or comp <= 1:
            print(f"blkptr at {addr} has invalid COMPRESS {comp}")
            errors += 1
        lsz = Blkptr.bp_get_lsize(bp)
        psz = Blkptr.bp_get_psize(bp)
        if lsz > Blkptr.SPA_MAXBLOCKSIZE:
            print(f"blkptr at {addr} has invalid LSIZE {lsz}")
            errors += 1
        if psz > Blkptr.SPA_MAXBLOCKSIZE:
            print(f"blkptr at {addr} has invalid PSIZE {psz}")
            errors += 1
        if Blkptr.bp_is_embedded(bp):
            etype = BF64_GET(bp.blk_prop, 40, 8)
            if etype >= 3:
                print(f"blkptr at {addr} has invalid ETYPE {etype}")
                errors += 1
        return errors

    names = ["blkptr"]
    input_type = "blkptr_t *"

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        for bp in objs:
            if bp is None:
                print("<NULL>")
                continue
            if not Blkptr.__bp_is_hole(bp) and Blkptr.bp_validate(bp) != 0:
                continue
            bpi = BpInfo()
            if Blkptr.bp_is_embedded(bp) != 0:
                bpi.set_ndvas(0)
            else:
                bpi.set_ndvas(Blkptr.bp_get_ndvas(bp))
            for i in range(0, bpi.ndvas):
                vdev = Blkptr.dva_get_vdev(bp, i)
                offset = format(Blkptr.dva_get_offset(bp, i), 'x')
                asize = format(Blkptr.dva_get_asize(bp, i), 'x')
                print(f"DVA[{i}]=<{vdev}:{offset}:{asize}> ", end='')

            bpi.set_initial_props(bp)

            if Blkptr.bp_is_embedded(bp) != 0:
                etype = BF64_GET(bp.blk_prop, 40, 8)
                lsize = format(BF64_GET_SB(bp.blk_prop, 0, 25, 0, 1), 'x')
                psize = format(BF64_GET_SB(bp.blk_prop, 25, 7, 0, 1), 'x')
                print(
                    f"EMBEDDED [L{bpi.level} {bpi.get_ot_name()}] et={etype} ",
                    end='')
                print(f"{bpi.get_compstr()} size=", end='')
                print(f"{lsize}L/{psize}P birth={bpi.birth}L")
                continue
            if Blkptr.__bp_is_hole(bp):
                print(
                    f"HOLE [L{bpi.level} {bpi.get_ot_name()}] size={bpi.lsize}L ",
                    end='')
                print(f"birth={bpi.birth}L")
                continue
            if Blkptr.bp_is_redacted(bp):
                print(
                    f"REDACTED [L{bpi.level} {bpi.get_ot_name()}] size={bpi.lsize}L ",
                    end='')
                print(f"birth={bpi.birth}L")
                continue

            print(
                f"[L{bpi.level} {bpi.get_ot_name()}] {bpi.get_cksum_string()}",
                end='')
            print(
                f" {bpi.get_compstr()} {bpi.crypt} {bpi.get_endian()} {bpi.get_gang()}",
                end='')
            print(f" {bpi.get_dedup()} {bpi.copies} {bpi.lsize}L/{bpi.psize}P ",
                  end='')
            print(f"birth={bpi.birth}L/{bpi.pbirth}P", end='')
            print(
                f" fill={bpi.get_fill(bp)} cksum={bpi.c0}:{bpi.c1}:{bpi.c2}:{bpi.c3}"
            )
