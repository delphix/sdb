#
# Copyright 2019, 2023 Delphix
# Copyright 2023 Datto, Inc.
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

import os

import drgn
import sdb


def removeprefix(text: str, prefix: str) -> str:
    """
    Used to pretty-print enum names that have a common
    prefix and are used as output to the user.

    Note: Python 3.9 and newer have this function in their
    string library. So until then we use this..
    """
    return text[text.startswith(prefix) and len(prefix):]


def nicenum(num: int, suffix: str = "B") -> str:
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if num < 1024:
            return f"{int(num)}{unit}{suffix}"
        num = int(num / 1024)
    return "{int(num)}Y{suffix}"


def gethrtime() -> int:
    """
    The equivalent of gethrtime() in Linux SPL.

    Note that there should be a very minor lag in the order of
    nanoseconds as there is no set of fields that can give us
    that level of precision at all times.
    """
    tkr = sdb.get_object("tk_core").timekeeper.tkr_raw
    nsec = tkr.xtime_nsec >> tkr.shift
    sec = sdb.get_object("tk_core").timekeeper.raw_sec
    hrtime = sec * NANOSEC + nsec
    return int(hrtime)


def P2PHASE(x: drgn.Object, align: int) -> int:
    return int(x & (align - 1))


def BF64_DECODE(x: drgn.Object, low: int, length: int) -> int:
    return int(P2PHASE(x >> low, 1 << length))


def BF64_GET(x: drgn.Object, low: int, length: int) -> int:
    return BF64_DECODE(x, low, length)


def BF64_GET_SB(x: int, low: int, length: int, shift: int, bias: int) -> int:
    return (BF64_GET(x, low, length) + bias) << shift


def WEIGHT_IS_SPACEBASED(weight: int) -> bool:
    return weight == 0 or (BF64_GET(weight, 60, 1) != 0)


def WEIGHT_GET_INDEX(weight: int) -> int:
    return BF64_GET((weight), 54, 6)


def WEIGHT_GET_COUNT(weight: int) -> int:
    return BF64_GET((weight), 0, 54)


def BPE_GET_ETYPE(bp: drgn.Object) -> int:
    return BF64_GET(bp.blk_prop, 40, 8)


def BPE_GET_LSIZE(bp: drgn.Object) -> int:
    return BF64_GET_SB(bp.blk_prop, 0, 25, 0, 1)


def BPE_GET_PSIZE(bp: drgn.Object) -> int:
    return BF64_GET_SB(bp.blk_prop, 25, 7, 0, 1)


def BP_GET_LSIZE(bp: drgn.Object) -> int:
    if BP_IS_EMBEDDED(bp):
        if BPE_GET_ETYPE(bp) == BP_EMBEDDED_TYPE_DATA:
            return BPE_GET_LSIZE(bp)
        return 0
    return BF64_GET_SB(bp.blk_prop, 0, SPA_LSIZEBITS, SPA_MINBLOCKSHIFT, 1)


def BP_GET_PSIZE(bp: drgn.Object) -> int:
    if BP_IS_EMBEDDED(bp):
        return 0
    return BF64_GET_SB(bp.blk_prop, 16, SPA_PSIZEBITS, SPA_MINBLOCKSHIFT, 1)


def BP_GET_COMPRESS(bp: drgn.Object) -> int:
    return BF64_GET(bp.blk_prop, 32, SPA_COMPRESSBITS)


def BP_IS_EMBEDDED(bp: drgn.Object) -> bool:
    return bool(BF64_GET(bp.blk_prop, 39, 1))


def BP_GET_CHECKSUM(bp: drgn.Object) -> int:
    if BP_IS_EMBEDDED(bp):
        return ZIO_CHECKSUM_OFF
    return BF64_GET(bp.blk_prop, 40, 8)


def BP_GET_TYPE(bp: drgn.Object) -> int:
    return BF64_GET(bp.blk_prop, 48, 8)


def BP_GET_LEVEL(bp: drgn.Object) -> int:
    return BF64_GET(bp.blk_prop, 56, 5)


def BP_USES_CRYPT(bp: drgn.Object) -> bool:
    return bool(BF64_GET(bp.blk_prop, 61, 1))


def BP_IS_ENCRYPTED(bp: drgn.Object) -> bool:
    return (BP_USES_CRYPT(bp) and BP_GET_LEVEL(bp) <= 0 and
            DMU_OT_IS_ENCRYPTED(BP_GET_TYPE(bp)))


def BP_IS_AUTHENTICATED(bp: drgn.Object) -> bool:
    return (BP_USES_CRYPT(bp) and BP_GET_LEVEL(bp) <= 0 and
            not DMU_OT_IS_ENCRYPTED(BP_GET_TYPE(bp)))


def BP_HAS_INDIRECT_MAC_CKSUM(bp: drgn.Object) -> bool:
    return (BP_USES_CRYPT(bp) and BP_GET_LEVEL(bp) > 0)


def BP_GET_DEDUP(bp: drgn.Object) -> bool:
    return bool(BF64_GET(bp.blk_prop, 62, 1))


def BP_GET_BYTEORDER(bp: drgn.Object) -> int:
    return BF64_GET(bp.blk_prop, 63, 1)


def BP_GET_LAYER(bp: drgn.Object) -> int:
    if sdb.get_type('blkptr_t').has_member('blk_logical_birth'):
        return BF64_GET(bp.blk_logical_birth, 56, 8)
    return BF64_GET(bp.blk_birth, 56, 8)


def BP_LOGICAL_BIRTH(bp: drgn.Object) -> int:
    if sdb.get_type('blkptr_t').has_member('blk_logical_birth'):
        return BF64_GET(bp.blk_logical_birth, 0, 56)
    return BF64_GET(bp.blk_birth, 0, 56)


def BP_PHYSICAL_BIRTH(bp: drgn.Object) -> int:
    if sdb.get_type('blkptr_t').has_member('blk_physical_birth'):
        return BF64_GET(bp.blk_physical_birth, 0, 56)
    return BF64_GET(bp.blk_phys_birth, 0, 56)


def BP_GET_BIRTH(bp: drgn.Object) -> int:
    if BP_IS_EMBEDDED(bp):
        return 0
    if BP_PHYSICAL_BIRTH(bp):
        return BP_PHYSICAL_BIRTH(bp)
    return BP_LOGICAL_BIRTH(bp)


def BP_GET_FILL(bp: drgn.Object) -> int:
    if BP_IS_ENCRYPTED(bp):
        return BF64_GET(bp.blk_fill, 0, 32)
    if BP_IS_EMBEDDED(bp):
        return 1
    return int(bp.blk_fill)


def BP_GET_IV2(bp: drgn.Object) -> int:
    return BF64_GET(bp.blk_fill, 32, 32)


def BP_IS_GANG(bp: drgn.Object) -> bool:
    if BP_IS_EMBEDDED(bp):
        return False
    return bool(BF64_GET(bp.blk_dva[0].dva_word[1], 63, 1))


def BP_IS_REDACTED(bp: drgn.Object) -> bool:
    return (BP_IS_EMBEDDED(bp) and
            BPE_GET_ETYPE(bp) == BP_EMBEDDED_TYPE_REDACTED)


def BP_IS_HOLE(bp: drgn.Object) -> bool:
    return (not BP_IS_EMBEDDED(bp) and DVA_IS_EMPTY(bp.blk_dva[0]))


def BP_GET_NDVAS(bp: drgn.Object) -> int:
    if BP_IS_EMBEDDED(bp):
        return 0
    ndvas = 0
    for d in range(0, 3):
        ndvas += DVA_GET_ASIZE(bp.blk_dva[d]) != 0
    return ndvas


def DVA_GET_ASIZE(dva: drgn.Object) -> int:
    return BF64_GET_SB(dva.dva_word[0], 0, SPA_ASIZEBITS, SPA_MINBLOCKSHIFT, 0)


def DVA_GET_VDEV(dva: drgn.Object) -> int:
    return BF64_GET(dva.dva_word[0], 32, SPA_VDEVBITS)


def DVA_GET_OFFSET(dva: drgn.Object) -> int:
    return BF64_GET_SB(dva.dva_word[1], 0, 63, SPA_MINBLOCKSHIFT, 0)


def DVA_IS_VALID(dva: drgn.Object) -> bool:
    return DVA_GET_ASIZE(dva) != 0


def DVA_IS_EMPTY(dva: drgn.Object) -> bool:
    return bool(dva.dva_word[0] == 0 and dva.dva_word[1] == 0)


def DMU_OT_IS_ENCRYPTED(ot: int) -> bool:
    if ot & DMU_OT_NEWTYPE:
        return bool(ot & DMU_OT_ENCRYPTED)
    return bool(sdb.get_object("dmu_ot")[ot].ot_encrypt)


SPA_LSIZEBITS = 16
SPA_PSIZEBITS = 16
SPA_ASIZEBITS = 24
SPA_COMPRESSBITS = 7
SPA_VDEVBITS = 24
SPA_MINBLOCKSHIFT = 9

ZIO_CHECKSUM_OFF = 2

DMU_OT_ENCRYPTED = 0x20
DMU_OT_NEWTYPE = 0x80

BP_EMBEDDED_TYPE_DATA = 0
BP_EMBEDDED_TYPE_RESERVED = 1
BP_EMBEDDED_TYPE_REDACTED = 2

METASLAB_WEIGHT_PRIMARY = int(1 << 63)
METASLAB_WEIGHT_SECONDARY = int(1 << 62)
METASLAB_WEIGHT_CLAIM = int(1 << 61)
METASLAB_WEIGHT_TYPE = int(1 << 60)
METASLAB_ACTIVE_MASK = (METASLAB_WEIGHT_PRIMARY | METASLAB_WEIGHT_SECONDARY |
                        METASLAB_WEIGHT_CLAIM)
BTREE_LEAF_SIZE = 4096
NANOSEC = 1_000_000_000
MSEC = 1_000
