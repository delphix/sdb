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


def WEIGHT_IS_SPACEBASED(weight: int) -> bool:
    return weight == 0 or (BF64_GET(weight, 60, 1) != 0)


def WEIGHT_GET_INDEX(weight: int) -> int:
    return BF64_GET((weight), 54, 6)


def WEIGHT_GET_COUNT(weight: int) -> int:
    return BF64_GET((weight), 0, 54)


METASLAB_WEIGHT_PRIMARY = int(1 << 63)
METASLAB_WEIGHT_SECONDARY = int(1 << 62)
METASLAB_WEIGHT_CLAIM = int(1 << 61)
METASLAB_WEIGHT_TYPE = int(1 << 60)
METASLAB_ACTIVE_MASK = (METASLAB_WEIGHT_PRIMARY | METASLAB_WEIGHT_SECONDARY |
                        METASLAB_WEIGHT_CLAIM)
BTREE_LEAF_SIZE = 4096
NANOSEC = 1_000_000_000
MSEC = 1_000
