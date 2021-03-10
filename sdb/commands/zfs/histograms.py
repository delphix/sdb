#
# Copyright 2020 Delphix
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
from sdb.commands.internal import fmt


class ZFSHistogram(sdb.Command):
    """
    Print ZFS Histogram and print its median segment size.

    NOTE
        The median is just an approximation as we can't tell the
        exact size of each bucket within a histogram bucket.

    EXAMPLES
        Dump the histogram of the normal metaslab class of the rpool:

            sdb> spa rpool | member spa_normal_class.mc_histogram | zhist
            seg-size   count
            --------   -----
              512.0B:   4359 *******************
               1.0KB:   3328 ***************
               2.0KB:   3800 *****************
               4.0KB:   3536 ***************
               8.0KB:   3983 *****************
              16.0KB:   4876 *********************
              32.0KB:   9138 ****************************************
              64.0KB:   4508 ********************
             128.0KB:   2783 ************
             256.0KB:   1952 *********
             512.0KB:   1218 *****
               1.0MB:    675 ***
               2.0MB:    486 **
               4.0MB:    267 *
               8.0MB:    110
              16.0MB:     50
              32.0MB:     18
              64.0MB:      8
             128.0MB:     11
             256.0MB:    102
            Approx. Median: 339.7MB
    """

    names = ["zfs_histogram", "zhist"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("offset", nargs="?", default=0, type=int)
        return parser

    @staticmethod
    def histogram_median(hist: drgn.Object, offset: int = 0) -> int:
        """
        Returns the approximated median of a ZFS histogram.
        """
        canonical_type = sdb.type_canonicalize(hist.type_)
        assert canonical_type.kind == drgn.TypeKind.ARRAY
        assert sdb.type_canonicalize(
            canonical_type.type).kind == drgn.TypeKind.INT

        total_space = 0
        for (bucket, value) in enumerate(hist):
            total_space += int(value) << (bucket + offset)

        if total_space == 0:
            return 0

        space_left, median = total_space / 2, 0
        for (bucket, value) in enumerate(hist):
            space_in_bucket = int(value) << (bucket + offset)
            if space_left <= space_in_bucket:
                median = 1 << (bucket + offset - 1)
                #
                # Size of segments may vary within one bucket thus we
                # attempt to approximate the median by looking at the
                # number of segments in the bucket and assuming that
                # they are evenly distributed along the bucket's range.
                #
                bucket_fill = space_left / space_in_bucket
                median += round(median * bucket_fill)
                break
            space_left -= space_in_bucket
        return median

    @staticmethod
    def print_histogram_median(hist: drgn.Object,
                               offset: int = 0,
                               indent: int = 0) -> None:
        median = ZFSHistogram.histogram_median(hist, offset)
        if median > 0:
            print(f'{" " * indent}Approx. Median: {fmt.size_nicenum(median)}')

    @staticmethod
    def print_histogram(hist: drgn.Object,
                        offset: int = 0,
                        indent: int = 0) -> None:
        canonical_type = sdb.type_canonicalize(hist.type_)
        assert canonical_type.kind == drgn.TypeKind.ARRAY
        assert sdb.type_canonicalize(
            canonical_type.type).kind == drgn.TypeKind.INT

        max_count = 0
        min_bucket = (len(hist) - 1)
        max_bucket = 0
        for (bucket, value) in enumerate(hist):
            count = int(value)
            if bucket < min_bucket and count > 0:
                min_bucket = bucket
            if bucket > max_bucket and count > 0:
                max_bucket = bucket
            if count > max_count:
                max_count = count

        HISTOGRAM_WIDTH_MAX = 40
        if max_count < HISTOGRAM_WIDTH_MAX:
            max_count = HISTOGRAM_WIDTH_MAX

        if min_bucket > max_bucket:
            print(f'{" " * indent}** No histogram data available **')
            return

        print(f'{" " * indent}seg-size   count')
        print(f'{" " * indent}{"-" * 8}   {"-" * 5}')

        for bucket in range(min_bucket, max_bucket + 1):
            count = int(hist[bucket])
            stars = round(count * HISTOGRAM_WIDTH_MAX / max_count)
            print(f'{" " * indent}{fmt.size_nicenum(2**(bucket+offset)):>8}: '
                  f'{count:>6} {"*" * stars}')

        ZFSHistogram.print_histogram_median(hist, offset, indent)

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        for obj in objs:
            ZFSHistogram.print_histogram(obj, self.args.offset)
