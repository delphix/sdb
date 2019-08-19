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


class ARCStats(sdb.Locator, sdb.PrettyPrinter):
    names = ["arc"]
    input_type = "arc_stats_t *"
    output_type = "arc_stats_t *"

    def print_stats(self, obj: drgn.Object) -> None:
        names = [
            tuple_[1] for tuple_ in self.prog.type('struct arc_stats').members
        ]

        for name in names:
            print("{:32} = {}".format(name, int(obj.member_(name).value.ui64)))

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        for obj in objs:
            self.print_stats(obj)

    def no_input(self) -> Iterable[drgn.Object]:
        yield self.prog["arc_stats"].address_of_()
