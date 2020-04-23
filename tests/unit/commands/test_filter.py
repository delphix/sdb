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

from tests.unit import invoke, MOCK_PROGRAM


def test_no_arg() -> None:
    line = 'filter'

    with pytest.raises(sdb.CommandArgumentsError):
        invoke(MOCK_PROGRAM, [], line)


def test_no_rhs() -> None:
    line = 'filter obj =='

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, [], line)


def test_no_lhs() -> None:
    line = 'filter == obj'

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, [], line)


def test_no_operator() -> None:
    line = 'filter obj'

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, [], line)


def test_single_void_ptr_input_lhs_not_object() -> None:
    line = 'filter 0 == obj'
    objs = [drgn.Object(MOCK_PROGRAM, 'void *', value=0)]

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, objs, line)


def test_multi_void_ptr_input_value_match_ne() -> None:
    line = 'filter "obj != 1"'
    objs = [
        drgn.Object(MOCK_PROGRAM, 'void *', value=0),
        drgn.Object(MOCK_PROGRAM, 'void *', value=1),
        drgn.Object(MOCK_PROGRAM, 'void *', value=2),
    ]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 2
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[1].value_() == 2
    assert ret[1].type_ == MOCK_PROGRAM.type('void *')


def test_char_array_input_object_match() -> None:
    line = 'filter obj == obj'
    objs = [drgn.Object(MOCK_PROGRAM, 'char [4]', value=b"foo")]

    with pytest.raises(sdb.CommandError):
        invoke(MOCK_PROGRAM, objs, line)


def test_struct_input_invalid_syntax() -> None:
    line = 'filter obj->ts_int == 1'
    objs = [MOCK_PROGRAM["global_struct"]]

    with pytest.raises(sdb.CommandEvalSyntaxError):
        invoke(MOCK_PROGRAM, objs, line)


def test_struct_input_bogus_member() -> None:
    line = 'filter obj.ts_bogus == 1'
    objs = [MOCK_PROGRAM["global_struct"]]

    with pytest.raises(sdb.CommandError):
        invoke(MOCK_PROGRAM, objs, line)
