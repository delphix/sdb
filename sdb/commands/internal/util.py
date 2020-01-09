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

import drgn
import sdb


def get_valid_struct_name(cmd: sdb.Command, tname: str) -> str:
    """
    If tname is a name of a type that's a typedef to a
    struct, this function return will it as is. If this
    is a name of a struct, then it returns the canonical
    name (e.g. adds "struct" prefix). Otherwise, raises
    an error.

    Used for shorthands in providing names of structure
    types to be consumed by drgn interfaces in string
    form (linux_list, container_of, etc..).
    """
    if tname in ['struct', 'union', 'class']:
        #
        # Note: We have to do this because currently in drgn
        # prog.type('struct') returns a different error than
        # prog.type('bogus'). The former returns a SyntaxError
        # "null identifier" while the latter returns LookupError
        # "could not find typedef bogus". The former is not
        # user-friendly and thus we just avoid that situation
        # by instructing the user to skip such keywords.
        #
        raise sdb.CommandError(cmd.name,
                               f"skip keyword '{tname}' and try again")

    try:
        type_ = sdb.get_prog().type(tname)
    except LookupError:
        # Check for struct
        struct_name = f"struct {tname}"
        try:
            type_ = sdb.get_prog().type(struct_name)
        except LookupError as err:
            raise sdb.CommandError(cmd.name, str(err))
        return struct_name

    # Check for typedef to struct
    if type_.kind != drgn.TypeKind.TYPEDEF:
        raise sdb.CommandError(
            cmd.name, f"{tname} is not a struct nor a typedef to a struct")
    if sdb.type_canonicalize(type_).kind != drgn.TypeKind.STRUCT:
        raise sdb.CommandError(cmd.name,
                               f"{tname} is not a typedef to a struct")
    return tname
