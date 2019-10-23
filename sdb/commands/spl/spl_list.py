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


class SPLList(sdb.Walker):
    names = ["spl_list"]
    input_type = "list_t *"

    def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        offset = int(obj.list_offset)
        first_node = obj.list_head.address_of_()
        node = first_node.next
        while node != first_node:
            yield drgn.Object(self.prog,
                              type="void *",
                              value=int(node) - offset)
            node = node.next
