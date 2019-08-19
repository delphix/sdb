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


class PrettyPrint(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["pretty_print", "pp"]

    def call(self, objs: Iterable[drgn.Object]) -> None:  # type: ignore
        baked = [(self.prog.type(type_), class_)
                 for type_, class_ in sdb.PrettyPrinter.all_printers.items()]
        has_input = False
        for i in objs:
            has_input = True

            try:
                for type_, class_ in baked:
                    if i.type_ == type_ and hasattr(class_, "pretty_print"):
                        class_(self.prog).pretty_print([i])
                        raise StopIteration
            except StopIteration:
                continue

            # error
            raise TypeError(
                'command "{}" does not handle input of type {}'.format(
                    self.names, i.type_))
        # If we got no input and we're the last thing in the pipeline, we're
        # probably the first thing in the pipeline. Print out the available
        # pretty-printers.
        if not has_input and self.islast:
            print("The following types have pretty-printers:")
            print("\t%-20s %-20s" % ("PRINTER", "TYPE"))
            for type_, class_ in baked:
                if hasattr(class_, "pretty_print"):
                    print("\t%-20s %-20s" % (class_(self.prog).names, type_))
