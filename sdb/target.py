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

from typing import Any, Union

import drgn

# pylint: disable=missing-function-docstring
# pylint: disable=global-statement
prog: drgn.Program


def get_type(type_name: str) -> drgn.Type:
    global prog
    return prog.type(type_name)


def get_pointer_type(type_name: str) -> drgn.Type:
    global prog
    return prog.pointer_type(type_name)


def get_typed_null(type_name: str) -> drgn.Object:
    global prog
    return drgn.NULL(prog, type_name)


def create_object(type_: Union[str, drgn.Type], val: Any) -> drgn.Object:
    global prog
    return drgn.Object(prog, type_, value=val)


def get_target_flags() -> drgn.ProgramFlags:
    global prog
    return prog.flags


def get_object(obj_name: str) -> drgn.Object:
    global prog
    return prog[obj_name]


def get_symbol(sym: Union[str, int]) -> drgn.Symbol:
    global prog
    return prog.symbol(sym)


def get_prog() -> drgn.Program:
    global prog
    return prog


def set_prog(myprog: drgn.Program) -> None:
    global prog
    prog = myprog
