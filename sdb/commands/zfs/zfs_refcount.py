#
# Copyright 2020 Datto, Inc.
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
from sdb.commands.spl.spl_list import SPLList


class Zfs_Refcount(sdb.PrettyPrinter):
    names = ["zfs_refcount"]
    input_type = "zfs_refcount_t *"
    output_type = "zfs_refcount_t *"

    @staticmethod
    def print_ref(obj: drgn.Object) -> None:
        ptr = int(obj.ref_holder)
        c = sdb.create_object("char *", ptr)
        try:
            s = c.string_().decode("utf-8")
        except UnicodeDecodeError:
            s = ""
        print(f"{hex(ptr)}   {s} ")

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        for zr in objs:
            # handle the lack of rc_tracked in non-debug zfs build
            tracked = 0
            try:
                tracked = zr.rc_tracked
            except AttributeError:
                pass
            print(f"zfs_recount_t at {hex(zr)} has {int(zr.rc_count)} "
                  f"current holds tracked={int(tracked)}")
            if tracked:
                ref_list = zr.rc_list
                list_addr = ref_list.address_of_()
                refs = sdb.execute_pipeline(
                    [list_addr],
                    [SPLList(), sdb.Cast(["reference_t *"])],
                )

                for ref in refs:
                    Zfs_Refcount.print_ref(ref)
