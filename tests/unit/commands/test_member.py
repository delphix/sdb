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
    line = 'member'

    with pytest.raises(sdb.CommandArgumentsError):
        invoke(MOCK_PROGRAM, [], line)


def test_scalar_input() -> None:
    line = 'addr global_int | member int_member'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "'int' is not a structure, union, or class" in str(err.value)


def test_member_not_found() -> None:
    line = 'addr global_struct | member bogus'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "'struct test_struct' has no member 'bogus'" in str(err.value)


def test_array_member_incomplete_expression() -> None:
    line = 'addr global_struct | member ts_array[2'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "incomplete array expression" in str(err.value)


def test_array_member_bogus_index() -> None:
    line = 'addr global_struct | member ts_array[a]'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "incorrect index: 'a' is not a number" in str(err.value)


def test_embedded_struct_member_deref_notation_error() -> None:
    line = 'addr global_cstruct | member cs_struct->ts_int'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "use the dot(.) notation for member access" in str(err.value)


def test_arrow_with_no_identifier() -> None:
    line = 'addr global_cstruct | member cs_struct->'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "no identifier specified after ->" in str(err.value)


def test_dot_with_no_identifier() -> None:
    line = 'addr global_cstruct | member cs_struct.'

    with pytest.raises(sdb.CommandError) as err:
        invoke(MOCK_PROGRAM, [], line)

    assert "no identifier specified after ." in str(err.value)
