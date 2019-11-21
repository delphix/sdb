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

import itertools
import drgn
import sdb


class PrettyPrint(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["pretty_print", "pp"]

    def call(self, objs: Iterable[drgn.Object]) -> None:  # type: ignore
        baked = [(self.prog.type(type_), class_)
                 for type_, class_ in sdb.PrettyPrinter.all_printers.items()]
        handlingClass = None
        inputType = None
        firstObj = next(iter(objs), None)
        if firstObj:
            inputType = firstObj.type_
            for type_, class_ in baked:
                if type_ == inputType and hasattr(class_, "pretty_print"):
                    handlingClass = class_
                    break

        if not handlingClass:
            print("The following types have pretty-printers:")
            print("\t%-20s %-20s" % ("PRINTER", "TYPE"))
            for type_, class_ in baked:
                if hasattr(class_, "pretty_print"):
                    print("\t%-20s %-20s" % (class_.names[0], type_))
            if inputType:
                msg = 'could not find pretty-printer for type {}'.format(
                    inputType)
            else:
                msg = 'could not find appropriate pretty-printer'
            raise sdb.CommandError(self.name, msg)

        handlingClass(self.prog).pretty_print(itertools.chain([firstObj], objs))
