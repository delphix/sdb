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

    assert "'int' is not a structure or union" in str(err.value)


def test_member_not_found():
    line = 'addr global_struct | member bogus'
    objs = []

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, objs, line)

    assert "'struct test_struct' has no member 'bogus'" in str(err.value)


def test_one_member():
    line = 'addr global_struct | member ts_int'
    objs = []

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0] == drgn.Object(MOCK_PROGRAM,
                                 MOCK_PROGRAM.type('int'),
                                 value=1)
