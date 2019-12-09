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
        baked = {
            sdb.type_canonicalize_name(type_): class_
            for type_, class_ in sdb.PrettyPrinter.all_printers.items()
        }

        handling_class = None
        first_obj_type, objs = sdb.get_first_type(objs)
        if first_obj_type is not None:
            first_obj_type_name = sdb.type_canonical_name(first_obj_type)
            if first_obj_type_name in baked:
                handling_class = baked[first_obj_type_name]

        if handling_class is None:
            if first_obj_type is not None:
                msg = 'could not find pretty-printer for type {}\n'.format(
                    first_obj_type)
            else:
                msg = 'could not find pretty-printer\n'
            msg += "The following types have pretty-printers:\n"
            msg += f"\t{'PRINTER':<20s} {'TYPE':<20s}\n"
            for type_name, class_ in sdb.PrettyPrinter.all_printers.items():
                msg += f"\t{class_.names[0]:<20s} {type_name:<20s}\n"
            raise sdb.CommandError(self.name, msg)

        handling_class().pretty_print(objs)
