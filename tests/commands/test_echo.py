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

import drgn
import pytest
import sdb

from tests import invoke, MOCK_PROGRAM


def test_empty():
    line = 'echo'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert not ret


def test_piped_input():
    line = 'echo'
    objs = [drgn.Object(MOCK_PROGRAM, 'void *', value=0)]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')


def test_single_arg_hex():
    line = 'echo 0x0'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')


def test_single_arg_decimal():
    line = 'echo 0'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')


def test_bogus_arg():
    line = 'echo bogus'
    objs = []

    with pytest.raises(sdb.CommandInvalidInputError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert err.value.argument == 'bogus'


def test_test_piped_int():
    line = 'echo'
    objs = [drgn.Object(MOCK_PROGRAM, 'int', value=1)]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 1
    assert ret[0].type_ == MOCK_PROGRAM.type('int')


def test_single_arg():
    line = 'echo 1'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 1
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')


def test_multiple_piped():
    line = 'echo'
    objs = [
        drgn.Object(MOCK_PROGRAM, 'void *', value=0),
        drgn.Object(MOCK_PROGRAM, 'int', value=1),
    ]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 2
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[1].value_() == 1
    assert ret[1].type_ == MOCK_PROGRAM.type('int')


def test_multiple_args():
    line = 'echo 0 1'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 2
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[1].value_() == 1
    assert ret[1].type_ == MOCK_PROGRAM.type('void *')


def test_piped_and_args_combo():
    line = 'echo 0 1'
    objs = [
        drgn.Object(MOCK_PROGRAM, 'void *', value=0),
        drgn.Object(MOCK_PROGRAM, 'int', value=1),
    ]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 4
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[1].value_() == 1
    assert ret[1].type_ == MOCK_PROGRAM.type('int')
    assert ret[2].value_() == 0
    assert ret[2].type_ == MOCK_PROGRAM.type('void *')
    assert ret[3].value_() == 1
    assert ret[3].type_ == MOCK_PROGRAM.type('void *')


def test_multi_echo_combo():
    line = 'echo 2 3 | echo 4'
    objs = [
        drgn.Object(MOCK_PROGRAM, 'void *', value=0),
        drgn.Object(MOCK_PROGRAM, 'int', value=1),
    ]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 5
    assert ret[0].value_() == 0
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[1].value_() == 1
    assert ret[1].type_ == MOCK_PROGRAM.type('int')
    assert ret[2].value_() == 2
    assert ret[2].type_ == MOCK_PROGRAM.type('void *')
    assert ret[3].value_() == 3
    assert ret[3].type_ == MOCK_PROGRAM.type('void *')
    assert ret[4].value_() == 4
    assert ret[4].type_ == MOCK_PROGRAM.type('void *')
