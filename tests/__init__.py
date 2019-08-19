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

from typing import Iterable, List, Optional

import drgn
import sdb


def create_struct_type(name: str, member_names: List[str],
                       member_types: List[drgn.Type]) -> drgn.Type:
    """
    Creates a structure type given a list of member names and
    a list of types like this:
    ```
    create_struct_type(<name>, [<name_a>, <name_b> ...],
                       [<type_a>, <type_b>, ...])
    ```
    returns a C structure:
    ```
    struct <name> {
      type_a name_a;
      type_b name_b;
      ...
    };
    ```
    """
    assert len(member_names) == len(member_types)
    struct_size, bit_offset = 0, 0
    member_list = []
    for member_name, type_ in zip(member_names, member_types):
        member_tuple = (type_, member_name, bit_offset, 0)
        member_list.append(member_tuple)
        bit_offset += 8 * struct_size
        struct_size += type_.size
    return drgn.struct_type(name, struct_size, member_list)


def setup_basic_mock_program() -> drgn.Program:
    #
    # We specify an architecture here so we can have consistent
    # results through explicit assumptions like size of pointers
    # and representation of integers.
    #
    platform = drgn.Platform(
        drgn.Architecture.X86_64,
        drgn.PlatformFlags.IS_LITTLE_ENDIAN | drgn.PlatformFlags.IS_64_BIT)
    prog = drgn.Program(platform)

    #
    # We create these types BEFORE registering the type callback
    # below and outside of the callback itself but access them
    # thorugh the closure of the outer function. This is because
    # calling prog.type() from within the callback itself can
    # lead to infinite recursion, and not using prog from withing
    # the callback means that we'd need to recreate basic types
    # like int and void *.
    #
    int_type = prog.type('int')
    voidp_type = prog.type('void *')
    struct_type = create_struct_type('test_struct', ['ts_int', 'ts_voidp'],
                                     [int_type, voidp_type])

    def mock_type_find(kind: drgn.TypeKind, name: str,
                       filename: Optional[str]) -> Optional[drgn.Type]:
        assert filename is None
        mocked_types = {
            'test_struct': struct_type,
        }
        if name in mocked_types:
            assert kind == mocked_types[name].kind
            return mocked_types[name]
        return None

    prog.add_type_finder(mock_type_find)

    global_struct_addr = 0xffffffffc0a8aee0

    def mock_object_find(prog: drgn.Program, name: str,
                         flags: drgn.FindObjectFlags,
                         filename: Optional[str]) -> Optional[drgn.Object]:
        assert filename is None
        assert flags == drgn.FindObjectFlags.ANY

        mock_objects = {
            'global_int': (int_type, 0xffffffffc0a8aee0),
            'global_void_ptr': (voidp_type, 0xffff88d26353c108),
            'global_struct': (struct_type, global_struct_addr),
        }

        if name in mock_objects:
            type_, addr = mock_objects[name]
            return drgn.Object(prog, type=type_, address=addr)
        return None

    prog.add_object_finder(mock_object_find)

    def fake_memory_reader(address: int, count: int, physical: int,
                           offset: bool) -> bytes:
        assert address == physical
        assert not offset
        fake_mappings = {
            # address of global_struct and its first member ts_int
            global_struct_addr: b'\x01\x00\x00\x00'
        }
        assert address in fake_mappings
        assert count == len(fake_mappings[address])
        return fake_mappings[address]

    prog.add_memory_segment(0, 0xffffffffffffffff, fake_memory_reader)
    return prog


#
# Basic mock program to be used by the very primitive commands
# like echo, address, member, cast, head, tail, filter, and help.
#
MOCK_PROGRAM = setup_basic_mock_program()


def invoke(prog: drgn.Program, objs: Iterable[drgn.Object],
           line: str) -> Iterable[drgn.Object]:
    """
    Dispatch to sdb.invoke, but also drain the generator it returns, so
    the tests can more easily access the returned objects.
    """
    return [i for i in sdb.invoke(prog, objs, line)]
