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

    names = ["pretty_print", "pp"]

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        baked = [(sdb.get_type(type_), class_)
                 for type_, class_ in sdb.PrettyPrinter.all_printers.items()]
        handlingClass = None
        first_obj_type, objs = sdb.get_first_type(objs)
        if first_obj_type is not None:
            for type_, class_ in baked:
                if type_ == first_obj_type and hasattr(class_, "pretty_print"):
                    handlingClass = class_
                    break

        if not handlingClass:
            print("The following types have pretty-printers:")
            print("\t%-20s %-20s" % ("PRINTER", "TYPE"))
            for type_, class_ in baked:
                if hasattr(class_, "pretty_print"):
                    print("\t%-20s %-20s" % (class_.names[0], type_))
            if first_obj_type:
                msg = 'could not find pretty-printer for type {}'.format(
                    first_obj_type)
            else:
                msg = 'could not find appropriate pretty-printer'
            raise sdb.CommandError(self.name, msg)

        handlingClass().pretty_print(objs)
