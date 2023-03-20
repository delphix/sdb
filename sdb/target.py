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
"""
This module attempts to abstract out most of the functionality
provided by the drgn.Program that we are using for the current
context of a running SDB instance. Its current form can be
thought of as a singleton class where the infrastructure will
initialize the `prog` global once and the consumers of the
infrastructure will be using the helper methods defined in
it to query information from the target.

That said, there are still edge cases when consumers may still
want the actual drgn.Program object (e.g. they are using the
stack_trace() or list_for_each() helpers of the drgn API). While
those consumers could import the `prog` global variable from
this module directly (e.g. `from sdb.target import prog`), we'd
rather them not and so we provide the get_prog() wrapper for it
that is exposed by the `sdb` module/package (our "public" API
that is exposed through the usual `import sdb`). The reason
for this is two-fold: [1] It makes the API simpler (only one
package to import) while also providing a better abstraction
for future changes in the infrastructure. [2] It reduces the
chance of potential cyclic imports in future refactoring.

Note that none of the wrappers below do any exception handling.
Consumers still need to do their own exception handling for
now as they have more important information on their context
for their user (e.g. command name).
"""

from typing import Any, List, Tuple, Union

import drgn

# pylint: disable=missing-function-docstring
# pylint: disable=global-statement
prog: drgn.Program


def get_type(type_name: str) -> drgn.Type:
    return prog.type(type_name)


def get_pointer_type(type_name: str) -> drgn.Type:
    return prog.pointer_type(type_name)


def is_null(obj: drgn.Object) -> bool:
    return bool(obj == drgn.NULL(prog, obj.type_))


def create_object(type_: Union[str, drgn.Type], val: Any) -> drgn.Object:
    return drgn.Object(prog, type_, value=val)


def get_target_flags() -> drgn.ProgramFlags:
    return prog.flags


def get_object(obj_name: str) -> drgn.Object:
    return prog[obj_name]


def get_symbol(sym: Union[str, int]) -> drgn.Symbol:
    return prog.symbol(sym)


def get_prog() -> drgn.Program:
    return prog


def set_prog(myprog: drgn.Program) -> None:
    global prog
    prog = myprog


def type_canonicalize(t: drgn.Type) -> drgn.Type:
    """
    Return the "canonical" version of this type.  This means removing
    qualifiers (const, volatile, etc) and typedef's.

    For example the type `foo_t*` will be canonicalized to `struct foo *`.

    Note: function type's arguments and return types are not canonicalized.
    """
    if t.kind == drgn.TypeKind.TYPEDEF:
        return type_canonicalize(t.type)
    if t.kind == drgn.TypeKind.POINTER:
        return prog.pointer_type(type_canonicalize(t.type), t.size)
    if t.kind == drgn.TypeKind.ARRAY:
        return prog.array_type(type_canonicalize(t.type), t.length)
    return t.unqualified()


def type_canonical_name(t: drgn.Type) -> str:
    """
    Return the "canonical name" of this type.  See type_canonicalize().
    """
    return str(type_canonicalize(t).type_name())


def type_canonicalize_name(type_name: str) -> str:
    """
    Return the "canonical name" of this type name.  See type_canonicalize().
    """
    #
    # This is a workaround while we don't have module/library lookup in drgn.
    # See https://github.com/delphix/cloud-init/issues/74 for details.
    #
    try:
        return type_canonical_name(prog.type(type_name))
    except LookupError:
        return type_name


def type_canonicalize_size(t: Union[drgn.Type, str]) -> int:
    """
    Return the "canonical size" of this type. See type_canonicalize().
    """
    if isinstance(t, str):
        type_ = get_type(t)
    else:
        assert isinstance(t, drgn.Type)
        type_ = t
    return int(type_canonicalize(type_).size)


def type_equals(a: drgn.Type, b: drgn.Type) -> bool:
    """
    This function determines if two types have the same canonical name. See
    type_canonicalize(). Note that two types may have the same canonical name
    and not actually be the same exact type, if they were definied in
    different source .c files. However, we can safely assume they are the
    same because we usually just need to know, "is this a foo_t*", without
    regard for which source .c file defined the foo_t.

    Note that the drgn type equality operator (==) attempts to evaluate deep
    type equality and therefore doesn't complete in a reasonable amount of time.
    "Deep type equality" means that two "struct foo"s that each contain a
    "struct bar *member" are not necessarily equal, because we must recursively
    check if each of their "struct bar"s are actually the same.
    """
    return type_canonical_name(a) == type_canonical_name(b)


#pylint: disable=too-few-public-methods
class All:
    """
    Commands that specify this runtime should always be loaded; these commands
    are universally applicable to all debugging scenarios.
    """


#pylint: disable=too-few-public-methods
class Kernel:
    """
    Commands that specify this runtime should be loaded any time a kernel
    is being analyzed.
    """


#pylint: disable=too-few-public-methods
class Userland:
    """
    Commands that specify this runtime should be loaded any time a userland
    program is being analyzed.
    """


#pylint: disable=too-few-public-methods
class Module:
    """
    Commands that specify this runtime should be loaded whenever the kernel
    module with the provided name is loaded.
    """

    def __init__(self, name: str) -> None:
        self.name = name


#pylint: disable=too-few-public-methods
class Library:
    """
    Commands that specify this runtime should be loaded whenever the library
    with the provided name is loaded.
    """

    def __init__(self, name: str) -> None:
        self.name = name


Runtime = Union[All, Kernel, Userland, Module, Library]


def get_runtimes() -> Tuple[bool, List[str]]:
    """
    Returns whether we are in kernel or user mode, and the list of loaded
    modules or libraries.
    """
    return (get_target_flags() & drgn.ProgramFlags.IS_LINUX_KERNEL, [])
