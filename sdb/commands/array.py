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


class Array(sdb.SingleInputCommand):
    """
    Walk through the objects of an array

    EXAMPLES
        Walk through all the `kmem_cache_node`s of a `kmem_cache`:

            sdb> slabs | head 1 | member node | array
            *(struct kmem_cache_node *)0xffff90cbd7fba4c0 = {
                ... <cropped> ...
            }
            *(struct kmem_cache_node *)0xffff90cbd7fba4c0 = {
                ... <cropped> ...
            }
            ... <cropped 1022 other elements> ...

        Ask for a specific size when it comes to zero-length arrays:

            sdb> zfs_dbgmsg | head 1 | member zdm_size
            (int)98
            sdb> zfs_dbgmsg | head 1 | member zdm_msg
            (char [1])"s"
            sdb> zfs_dbgmsg | head 1 | member zdm_msg | array 98
            warning: requested size 98 exceeds type size 1
            (char)115
            (char)112
            (char)97
            ... <cropped 95 other elements> ...

        The command also works with pointer arrays as long as the
        number of elements is specified:

            sdb> spa | member spa_zio_taskq[0][0].stqs_taskq
            *(taskq_t **)0xffff90cc154dcdc8 = 0xffff90cc127ea600

            sdb> spa | member spa_zio_taskq[0][0].stqs_taskq | array 2
            *(taskq_t *)0xffff90cc127ea600 = {
                ... <cropped> ...
            }
            *(taskq_t *)0xffff90cc181bfb00 = {
                ... <cropped> ...
            }

        Until a better way/notation is implemented on SDB the only
        way to ask for specific subranges of elements is through
        the addition of `head` and `tail` commands in the pipeline.
    """

    names = ["array"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("nelems",
                            type=int,
                            nargs="?",
                            help="number of elements in array to walk")
        return parser

    def _call_one(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        nelems = 0

        obj_type = sdb.type_canonicalize(obj.type_)
        if obj_type.kind == drgn.TypeKind.ARRAY and not obj_type.is_complete(
        ) and not obj.absent_:
            if self.args.nelems is None:
                err_msg = "zero-length array: please specify number of elements"
                raise sdb.CommandError(self.name, err_msg)
            print("warning: operating on zero-length array")
            nelems = self.args.nelems
        elif obj_type.kind == drgn.TypeKind.ARRAY:
            array_elems = len(obj)
            if self.args.nelems is not None:
                nelems = self.args.nelems
                if nelems > array_elems:
                    print(
                        f"warning: requested size {nelems} exceeds type size {array_elems}"
                    )
            else:
                nelems = array_elems

        elif obj_type.kind == drgn.TypeKind.POINTER:
            if self.args.nelems is None:
                err_msg = (f"'{obj.type_.type_name()}' is a pointer - "
                           "please specify the number of elements")
                raise sdb.CommandError(self.name, err_msg)
            nelems = self.args.nelems

            if not obj_type.type.is_complete():
                err_msg = ("can't walk pointer array of incomplete type "
                           f"'{obj_type.type.type_name()}'")
                raise sdb.CommandError(self.name, err_msg)
        else:
            raise sdb.CommandError(
                self.name,
                f"'{obj.type_.type_name()}' is not an array nor a pointer type")

        for i in range(nelems):
            yield obj[i]
