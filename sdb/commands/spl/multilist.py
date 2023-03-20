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
from sdb.commands.spl.spl_list import SPLList


class MultiList(sdb.Walker):
    names = ["multilist"]
    input_type = "multilist_t *"
    load_on = [sdb.Module("spl")]

    def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        for i in range(obj.ml_num_sublists):
            sublist = obj.ml_sublists[i].mls_list.address_of_()
            yield from sdb.execute_pipeline([sublist], [SPLList()])
