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
import sdb

from tests.unit import invoke, MOCK_PROGRAM


def test_no_arg() -> None:
    line = 'cast'

    with pytest.raises(sdb.CommandArgumentsError):
        invoke(MOCK_PROGRAM, [], line)


def test_arg_no_pipe_input() -> None:
    line = 'cast int'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert not ret


def test_arg_no_pipe_input_invalid_type() -> None:
    line = 'cast bogus'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "could not find type 'bogus'" in str(err.value)


def test_invoke_pipe_input() -> None:
    line = 'cast void *'
    objs = [MOCK_PROGRAM['global_int']]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[0].value_() == 0x01020304


def test_str_pipe_input() -> None:
    line = 'addr global_int | cast void *'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert len(ret) == 1
    assert ret[0].type_ == MOCK_PROGRAM.type('void *')
    assert ret[0].value_() == 0xffffffffc0000000


def test_pipe_input_pointer_to_int() -> None:
    line = 'addr global_int | cast unsigned int'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert len(ret) == 1
    assert ret[0].type_ == MOCK_PROGRAM.type('unsigned int')
    assert ret[0].value_() == 0xc0000000


def test_str_pipe_input_pointer_to_invalid_type() -> None:
    line = 'addr global_int | cast bogus'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "could not find type 'bogus'" in str(err.value)


def test_double_cast() -> None:
    line = 'addr global_int | cast unsigned int | cast char *'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert len(ret) == 1
    assert ret[0].type_ == MOCK_PROGRAM.type('char *')
    assert ret[0].value_() == 0xc0000000


def test_pointer_to_struct() -> None:
    line = 'addr global_int | cast struct test_struct'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "cannot convert 'int *' to 'struct test_struct'" in str(err.value)
