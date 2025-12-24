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


def get_valid_type_by_name(cmd: sdb.Command, tname: str) -> drgn.Type:
    """
    Given a type name in string form (`tname`) without any C keyword
    prefixes (e.g. 'struct', 'enum', 'class', 'union'), return the
    corresponding drgn.Type object. If `tname` starts with a C keyword
    we just return the type as is.

    This function is used primarily by commands that accept a type
    name as an argument and exist only to save keystrokes for the
    user.
    """
    TYPE_KEYWORDS = ['struct', 'enum', 'union', 'class']

    tokens = tname.split()
    if len(tokens) > 2:
        #
        # drgn fails in all kinds of ways when we pass it an
        # invalid type that consists of more than 2 text tokens.
        #
        raise sdb.CommandError(cmd.name,
                               f"input '{tname}' is not a valid type name")

    if len(tokens) == 2:
        if tokens[0] not in TYPE_KEYWORDS or tokens[1] in TYPE_KEYWORDS:
            #
            # For the same reason mentioned in the above comment
            # we also ensure that someone may not invalid two-token
            # input that has the following errors:
            # 1] Doesn't start with a type keyword - e.g "bogus type"
            # 2] Has a type keyword as its type name (also see
            #    comment below) - e.g. struct struct
            #
            raise sdb.CommandError(cmd.name,
                                   f"input '{tname}' is not a valid type name")
        try:
            return sdb.get_type(tname)
        except LookupError as err:
            raise sdb.CommandError(cmd.name,
                                   f"couldn't find type '{tname}'") from err
        except SyntaxError as err:
            raise sdb.CommandError(
                cmd.name, f"input '{tname}' is not a valid type name") from err

    if tname in TYPE_KEYWORDS:
        #
        # Note: We have to do this because currently in drgn
        # prog.type('struct') returns a different error than
        # prog.type('bogus'). The former returns a SyntaxError
        # "null identifier" while the latter returns LookupError
        # "could not find typedef bogus". The former is not
        # user-friendly and thus we just avoid that situation
        # by instructing the user to skip such keywords.
        #
        raise sdb.CommandError(
            cmd.name,
            f"skip keyword '{tname}' or quote your type \"{tname} <typename>\"")

    try:
        type_ = sdb.get_type(tname)
        if type_.kind == drgn.TypeKind.TYPEDEF and type_.type_name(
        ) == sdb.type_canonical_name(type_):
            #
            # In some C codebases there are typedefs like this:
            #
            #     typedef union GCObject GCObject; // taken from LUA repo
            #
            # The point of the above is to avoid typing the word
            # 'union' every time we declare a variable of that type.
            # For the purposes of SDB, passing around a drng.Type
            # describing the typedef above isn't particularly
            # useful. Using such an object with the `ptype` command
            # (one of the consumers of this function) would yield
            # the following:
            #
            #     sdb> ptype GCObject
            #     typedef union GCObject GCObject
            #
            # Resolving the typedef's explicitly in those cases
            # is more useful and this is why this if-clause exists.
            #
            #     sdb> ptype GCObject
            #     union GCObject {
            #             GCheader gch;
            #             union TString ts;
            #             ...
            #     }
            #
            return sdb.type_canonicalize(type_)
        return type_
    except LookupError:
        #
        # We couldn't find a type with that name. Check if
        # it is a structure, an enum, or a union.
        #
        pass
    except SyntaxError as err:
        raise sdb.CommandError(
            cmd.name, f"input '{tname}' is not a valid type name") from err
    for prefix in TYPE_KEYWORDS:
        try:
            return sdb.get_type(f"{prefix} {tname}")
        except LookupError:
            pass
    raise sdb.CommandError(
        cmd.name,
        f"couldn't find typedef, struct, enum, nor union named '{tname}'")


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
    type_ = get_valid_type_by_name(cmd, tname)

    if type_.kind == drgn.TypeKind.STRUCT:
        return str(type_.type_name())

    # canonicalize in case this is a typedef to a struct
    canonical_type_ = sdb.type_canonicalize(type_)
    if canonical_type_.kind == drgn.TypeKind.STRUCT:
        return str(canonical_type_.type_name())

    raise sdb.CommandError(
        cmd.name, f"{tname} is not a struct nor a typedef to a struct")


def removeprefix(text: str, prefix: str) -> str:
    """
    Used to pretty-print enum names that have a common
    prefix and are used as output to the user.

    Note: Python 3.9 and newer have this function in their
    string library. So until then we use this..
    """
    return text[text.startswith(prefix) and len(prefix):]
