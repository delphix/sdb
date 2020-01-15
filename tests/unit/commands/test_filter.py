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


def test_no_arg():
    line = 'filter'
    objs = []

    with pytest.raises(sdb.CommandArgumentsError):
        invoke(MOCK_PROGRAM, objs, line)


def test_no_rhs():
    line = 'filter obj =='
    objs = []

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, objs, line)


def test_no_lhs():
    line = 'filter == obj'
    objs = []

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, objs, line)


def test_no_operator():
    line = 'filter obj'
    objs = []

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, objs, line)


def test_single_void_ptr_input_lhs_not_object():
    line = 'filter 0 == obj'
    objs = [drgn.Object(MOCK_PROGRAM, 'void *', value=0)]

    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, objs, line)


def test_multi_void_ptr_input_value_match_ne():
    line = 'filter obj != 1'
    objs = [
        drgn.Object(MOCK_PROGRAM, 'void *', value=0),
        drgn.Object(MOCK_PROGRAM, 'void *', value=1),
        drgn.Object(MOCK_PROGRAM, 'void *', value=2),
    ]

    #
    # This throws an error for all the wrong reasons. The operator this
    # test is attempting to use is "!=", and due to a bug in the lexer
    # used within "invoke", this operator does not reach the "filter"
    # command. Instead, the lexer sees the "!" character and split the
    # string into the following parts:
    #
    #     1. filter obj
    #     2. = 1
    #
    # As a result, the "filter" command fails because it doesn't see a
    # comparison operator as input to it.
    #
    with pytest.raises(sdb.CommandInvalidInputError):
        invoke(MOCK_PROGRAM, objs, line)


def test_char_array_input_object_match():
    line = 'filter obj == obj'
    objs = [drgn.Object(MOCK_PROGRAM, 'char [4]', value=b"foo")]

    with pytest.raises(sdb.CommandError):
        invoke(MOCK_PROGRAM, objs, line)


def test_struct_input_invalid_syntax():
    line = 'filter obj->ts_int == 1'
    objs = [MOCK_PROGRAM["global_struct"]]

    with pytest.raises(sdb.CommandEvalSyntaxError):
        invoke(MOCK_PROGRAM, objs, line)


def test_struct_input_bogus_member():
    line = 'filter obj.ts_bogus == 1'
    objs = [MOCK_PROGRAM["global_struct"]]

    with pytest.raises(sdb.CommandError):
        invoke(MOCK_PROGRAM, objs, line)
