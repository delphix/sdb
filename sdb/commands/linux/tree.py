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
import drgn.helpers.linux.rbtree as drgn_rbtree

import sdb
from sdb.commands.internal.util import get_valid_struct_name


class RBTree(sdb.Command):
    """
    Walk a standard Linux Red-Black tree

    DESCRIPTION
        Given the type of its nodes and the name of its rb_node
        member, walk a red-black tree in-order as defined in the
        Linux kernel ('struct rb_root' type in include/linux/rbtree.h).

    EXAMPLES
        Walk all the vmalloc'd areas:

            sdb> addr vmap_area_root | rbtree vmap_area rb_node
            (struct vmap_area *)0xffff944ee6d47e18
            (struct vmap_area *)0xffff944ee6d47b00
            (struct vmap_area *)0xffff944ee6d476e0
            (struct vmap_area *)0xffff944ee6d47210
            (struct vmap_area *)0xffff944ee6d47160
    """

    names = ["rbtree"]
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "struct_name",
            help="name of the struct used for entries in the tree")
        parser.add_argument("member",
                            help="name of the node member within the struct")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        sname = get_valid_struct_name(self, self.args.struct_name)
        for obj in objs:
            try:
                yield from drgn_rbtree.rbtree_inorder_for_each_entry(
                    sname, obj, self.args.member)
            except LookupError as err:
                raise sdb.CommandError(self.name, str(err))
