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

from typing import Iterable, List, Optional

import drgn
import sdb


class Btree(sdb.Walker):
    """
    walk zfs_btree

    DESCRIPTION

        btree_t's are used in ZFS, especially as metaslab range trees. Use walk or
        zfs_btree for an in-order traversal of the contents of the tree.

    EXAMPLES

        > <metaslab_t *> | member ms_allocatable | walk | cast range_seg32_t *

        *(range_seg32_t *)0xffff9990b5141d68 = {
        .rs_start = (uint32_t)862981,
        .rs_end = (uint32_t)868158,
        }
        *(range_seg32_t *)0xffff9990b5141d70 = {
        .rs_start = (uint32_t)868163,
        .rs_end = (uint32_t)939419,
        }
        *(range_seg32_t *)0xffff9990b5141d78 = {
        .rs_start = (uint32_t)939424,
        .rs_end = (uint32_t)1048576,
        }
    """

    names = ["zfs_btree"]
    input_type = "zfs_btree_t *"

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.elem_size: drgn.Object = None

    def _val(self, start: int, idx: int) -> drgn.Object:
        location = start + (self.elem_size * idx)
        return sdb.create_object("void *", location)

    def _helper(self, node: drgn.Object) -> Iterable[drgn.Object]:
        if not node:
            return

        #
        # We check both members of the node because of the change introdcued in
        # https://github.com/delphix/zfs/commit/c0bf952c846100750f526c2a32ebec17694a201b
        #
        try:
            recurse = int(node.bth_first) == -1
        except AttributeError:
            recurse = node.bth_core

        count = node.bth_count
        if recurse:
            # alterate recursive descent on the children and generating core objects
            core = drgn.cast('struct zfs_btree_core *', node)
            for i in range(count):
                yield from self._helper(core.btc_children[i])
                yield self._val(core.btc_elems, i)
            # descend the final, far-right child node
            yield from self._helper(core.btc_children[count])
        else:
            # generate each object in the leaf elements
            leaf = drgn.cast('struct zfs_btree_leaf *', node)
            for i in range(count):
                yield self._val(leaf.btl_elems, i + node.bth_first)

    def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        self.elem_size = obj.bt_elem_size
        yield from self._helper(obj.bt_root)
