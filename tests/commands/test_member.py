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

import pytest
import drgn
import sdb

from tests import invoke, MOCK_PROGRAM


def test_no_arg():
    line = 'member'
    objs = []

    with pytest.raises(sdb.CommandArgumentsError):
        invoke(MOCK_PROGRAM, objs, line)


def test_arg_no_pipe_input():
    line = 'member int_member'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert not ret


def test_scalar_input():
    line = 'addr global_int | member int_member'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "'int' is not a structure, union, or class" in str(err.value)


def test_member_not_found():
    line = 'addr global_struct | member bogus'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "'struct test_struct' has no member 'bogus'" in str(err.value)


def test_first_member():
    line = 'addr global_struct | member ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == drgn.Object(MOCK_PROGRAM,
                                 MOCK_PROGRAM.type('int'),
                                 value=1)


def test_second_member():
    line = 'addr global_struct | member ts_voidp'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    #
    # We expect global_struct.ts_voidp to point to
    # global_int (see comment on fake_mappings).
    #
    assert len(ret) == 1
    assert ret[0] == MOCK_PROGRAM['global_int'].address_of_()


def test_multiple_members():
    line = 'addr global_struct | member ts_int ts_voidp'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 2
    assert ret[0] == drgn.Object(MOCK_PROGRAM,
                                 MOCK_PROGRAM.type('int'),
                                 value=1)
    assert ret[1] == MOCK_PROGRAM['global_int'].address_of_()


def test_array_member_index():
    line = 'addr global_struct | member ts_array[0]'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == drgn.Object(MOCK_PROGRAM,
                                 MOCK_PROGRAM.type('int'),
                                 value=0x0f0f0f0f)


def test_array_member_incomplete_expression():
    line = 'addr global_struct | member ts_array[2'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "incomplete array expression" in str(err.value)


def test_array_member_bogus_index():
    line = 'addr global_struct | member ts_array[a]'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "incorrect index: 'a' is not a number" in str(err.value)


def test_ptr_member():
    line = 'addr global_cstruct | member cs_structp'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    #
    # global_cstruct.cs_struct is expected to point
    # to global_strct (see comment on fake_mappings).
    #
    assert len(ret) == 1
    assert ret[0] == MOCK_PROGRAM['global_struct'].address_of_()


def test_ptr_member_deref_standard_c_notation():
    line = 'addr global_cstruct | member cs_structp->ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == MOCK_PROGRAM['global_struct'].ts_int


def test_ptr_member_deref_standard_c_notation_with_array_index():
    line = 'addr global_cstruct | member cs_structp->ts_array[1]'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == MOCK_PROGRAM['global_struct'].ts_array[1]


def test_ptr_member_deref_dot_notation():
    line = 'addr global_cstruct | member cs_structp.ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == MOCK_PROGRAM['global_struct'].ts_int


def test_ptr_member_deref_dot_notation_and_array_index():
    line = 'addr global_cstruct | member cs_structp.ts_array[1]'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == MOCK_PROGRAM['global_struct'].ts_array[1]


def test_embedded_struct_member():
    line = 'addr global_cstruct | member cs_struct.ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 0xA


def test_embedded_struct_member_deref_notation_error():
    line = 'addr global_cstruct | member cs_struct->ts_int'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "use the dot(.) notation for member access" in str(err.value)


def test_ptr_member_skip_null_deref():
    line = 'addr global_cstruct | member cs_structp_null->ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert not ret


def test_invalid_memory_casted_to_type_member():
    line = 'echo 0x0 | cast struct test_struct * | member ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert not ret


def test_arrow_with_no_identifier():
    line = 'addr global_cstruct | member cs_struct->'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "no identifier specified after ->" in str(err.value)


def test_dot_with_no_identifier():
    line = 'addr global_cstruct | member cs_struct.'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "no identifier specified after ." in str(err.value)
