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

import os
import time

import drgn
import sdb


def enum_lookup(enum_type_name: str, value: int) -> str:
    """return a string which is the short name of the enum value
    (truncating off the common prefix) """
    fields = sdb.get_type(enum_type_name).type.enumerators
    enum_string: str = fields[value].name
    prefix = os.path.commonprefix([f[0] for f in fields])
    return enum_string[prefix.rfind("_") + 1:]


def nicenum(num: int, suffix: str = "B") -> str:
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if num < 1024:
            return "{}{}{}".format(int(num), unit, suffix)
        num = int(num / 1024)
    return "{}{}{}".format(int(num), "Y", suffix)


def gethrtime() -> int:
    return int(time.clock_gettime(time.CLOCK_MONOTONIC) * NANOSEC)


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


METASLAB_WEIGHT_PRIMARY = int(1 << 63)
METASLAB_WEIGHT_SECONDARY = int(1 << 62)
METASLAB_WEIGHT_CLAIM = int(1 << 61)
METASLAB_WEIGHT_TYPE = int(1 << 60)
METASLAB_ACTIVE_MASK = (METASLAB_WEIGHT_PRIMARY | METASLAB_WEIGHT_SECONDARY |
                        METASLAB_WEIGHT_CLAIM)
BTREE_LEAF_SIZE = 4096
NANOSEC = 1000000000
MSEC = 1000
