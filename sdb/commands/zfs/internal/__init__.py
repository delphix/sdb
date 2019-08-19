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
# pylint: disable=unnecessary-lambda

import os
from typing import Callable

import drgn


def enum_lookup(prog, enum_type_name, value):
    """return a string which is the short name of the enum value
    (truncating off the common prefix) """
    fields = prog.type(enum_type_name).type.enumerators
    prefix = os.path.commonprefix([f[0] for f in fields])
    return fields[value][0][prefix.rfind("_") + 1:]


def print_histogram(histogram, size, offset):
    max_data = 0
    maxidx = 0
    minidx = size - 1

    for i in range(0, size):
        if histogram[i] > max_data:
            max_data = histogram[i]
        if histogram[i] > 0 and i > maxidx:
            maxidx = i
        if histogram[i] > 0 and i < minidx:
            minidx = i
    if max_data < 40:
        max_data = 40

    for i in range(minidx, maxidx + 1):
        print("%3u: %6u %s" %
              (i + offset, histogram[i], "*" * int(histogram[i])))


def nicenum(num, suffix="B"):
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if num < 1024:
            return "{}{}{}".format(int(num), unit, suffix)
        num /= 1024
    return "{}{}{}".format(int(num), "Y", suffix)


P2PHASE: Callable[[drgn.Object, int], drgn.Object] = lambda x, align: ((x) & (
    (align) - 1))
BF64_DECODE: Callable[[drgn.Object, int, int], int] = lambda x, low, len: int(
    P2PHASE(x >> low, 1 << len))
BF64_GET: Callable[[drgn.Object, int, int],
                   int] = lambda x, low, len: BF64_DECODE(x, low, len)


def WEIGHT_IS_SPACEBASED(weight):  # pylint: disable=invalid-name
    return weight == 0 or BF64_GET(weight, 60, 1)


def WEIGHT_GET_INDEX(weight):  # pylint: disable=invalid-name
    return BF64_GET((weight), 54, 6)


def WEIGHT_GET_COUNT(weight):  # pylint: disable=invalid-name
    return BF64_GET((weight), 0, 54)


METASLAB_WEIGHT_PRIMARY = int(1 << 63)
METASLAB_WEIGHT_SECONDARY = int(1 << 62)
METASLAB_WEIGHT_CLAIM = int(1 << 61)
METASLAB_WEIGHT_TYPE = int(1 << 60)
METASLAB_ACTIVE_MASK = (METASLAB_WEIGHT_PRIMARY | METASLAB_WEIGHT_SECONDARY |
                        METASLAB_WEIGHT_CLAIM)
