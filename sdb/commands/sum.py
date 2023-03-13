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

from typing import Iterable

import drgn
import sdb


class SdbSum(sdb.Command):
    """
    Sum integers passed through the pipe.

    EXAMPLES
        Print the number of bytes used by all the metaslab_t
        structures:

            sdb> spa | vdev | metaslab | deref | sizeof | sum
            (uint64_t)284672

        Print the number of bytes used by all the task_structs
        in the system:

            sdb> threads | deref | sizeof | sum
            (uint64_t)4548544
    """

    names = ["sum"]
    load_on = [sdb.All()]

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        result = 0
        for obj in objs:
            type_ = sdb.type_canonicalize(obj.type_)
            if type_.kind not in (drgn.TypeKind.INT, drgn.TypeKind.POINTER):
                raise sdb.CommandError(
                    self.name, f"'{type_.type_name()}' is not an integer type")
            result += int(obj.value_())
        yield sdb.create_object('uint64_t', result)
