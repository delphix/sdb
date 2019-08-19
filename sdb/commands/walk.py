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


# A convenience command that will automatically dispatch to the appropriate
# walker based on the type of the input data.
class Walk(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["walk"]

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        baked = [(self.prog.type(type_), class_)
                 for type_, class_ in sdb.Walker.allWalkers.items()]
        has_input = False
        for i in objs:
            has_input = True

            try:
                for type_, class_ in baked:
                    if i.type_ == type_:
                        yield from class_(self.prog).walk(i)
                        raise StopIteration
            except StopIteration:
                continue

            print("The following types have walkers:")
            print("\t%-20s %-20s" % ("WALKER", "TYPE"))
            for type_, class_ in baked:
                print("\t%-20s %-20s" % (class_(self.prog).names, type_))
            raise TypeError("no walker found for input of type {}".format(
                i.type_))
        # If we got no input and we're the last thing in the pipeline, we're
        # probably the first thing in the pipeline. Print out the available
        # walkers.
        if not has_input and self.islast:
            print("The following types have walkers:")
            print("\t%-20s %-20s" % ("WALKER", "TYPE"))
            for type_, class_ in baked:
                print("\t%-20s %-20s" % (class_(self.prog).names, type_))
