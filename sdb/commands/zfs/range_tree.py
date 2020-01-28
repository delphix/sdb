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

from typing import Iterable

import drgn
import sdb
from sdb.commands.zfs.btree import Btree
from sdb.command import Cast


class RangeTree(sdb.PrettyPrinter):
    names = ['range_tree']
    input_type = 'range_tree_t *'

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:

        # RangeTreeSeg is a SingleInputCommand, and it's like a pretty-printer
        # for range_seg*_t's, but since it has no `names`, it can't be invoked
        # from the command line. The reason is that range_seg*_t's specify their
        # ranges relative to rt_start/rt_shift, which are not accessible from
        # the range_seg*_t. Therefore, they can only be pretty-printed as part
        # of a range_tree_t*, from the range_tree pretty-printer.
        class RangeTreeSeg(sdb.SingleInputCommand):

            def __init__(self, rt: drgn.Object):
                super().__init__()
                self.rt = rt

            def _call_one(self, obj: drgn.Object) -> None:
                start = (obj.rs_start << self.rt.rt_shift) + self.rt.rt_start
                end = (obj.rs_end << self.rt.rt_shift) + self.rt.rt_start
                if hasattr(self.rt, 'rs_fill'):
                    fill = obj.rs_fill << self.rt.rt_shift
                    print(f"    [{hex(start)} {hex(end)}) "
                          f"(length {hex(end - start)}) "
                          f"(fill {hex(fill)})")
                else:
                    print(f"    [{hex(start)} {hex(end)}) "
                          f"(length {hex(end - start)})")

        for rt in objs:
            print(f"{hex(rt)}: range tree of {int(rt.rt_root.bt_num_elems)} "
                  f"entries, {int(rt.rt_space)} bytes")
            for _ in sdb.execute_pipeline([rt], [RangeSeg(), RangeTreeSeg(rt)]):
                pass


class RangeSeg(sdb.Locator):
    """
    Locate the range seg's associated with a range tree.

    Given a 'range_tree_t*', locate the range_seg's assocated with it.
    These may be type range_seg32_t*, range_seg64_t*, or range_seg_gap_t*,
    depending on what kind of range_tree_t this is.
    """
    names = ['range_seg']

    #pylint: disable=no-self-use
    @sdb.InputHandler('range_tree_t *')
    def from_range_tree(self, rt: drgn.Object) -> Iterable[drgn.Object]:
        enum_dict = dict(sdb.get_type('enum range_seg_type').enumerators)
        range_seg_type_to_type = {
            enum_dict['RANGE_SEG32']: 'range_seg32_t*',
            enum_dict['RANGE_SEG64']: 'range_seg64_t*',
            enum_dict['RANGE_SEG_GAP']: 'range_seg_gap_t*',
        }
        seg_type_name = range_seg_type_to_type[int(rt.rt_type)]
        yield from sdb.execute_pipeline([rt.rt_root.address_of_()],
                                        [Btree(), Cast(seg_type_name)])
