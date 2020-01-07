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


class Count(sdb.Command):
    """
    Return a count of the number of objects in the pipeline

    EXAMPLES
        Print the number of addresses given

            sdb> addr 0 | count
            (unsigned long long)1
            sdb> addr 0 | addr 1 | count
            (unsigned long long)2

        Print the number of ZFS dbufs

            sdb> dbuf | count
            (unsigned long long)19

        Print the number of root slab caches in the system

            sdb> slabs | count
            (unsigned long long)136

        Print the number of level 3 log statements in the kernel log buffer

            sdb> dmesg | filter obj.level == 3 | count
            (unsigned long long)24
    """

    names = ["count", "cnt", "wc"]

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        yield sdb.create_object('unsigned long long', sum(1 for _ in objs))
