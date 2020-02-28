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

from tests.unit import invoke, MOCK_PROGRAM


def test_empty() -> None:
    line = 'count'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert len(ret) == 1
    assert ret[0].value_() == 0


def test_single_piped_input() -> None:
    line = 'echo 0x0 | count'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert len(ret) == 1
    assert ret[0].value_() == 1


def test_multiple_piped_inputs() -> None:
    line = 'echo 0x0 0xfffff 0xdeadbeef 0x101010 | count'

    ret = invoke(MOCK_PROGRAM, [], line)

    assert len(ret) == 1
    assert ret[0].value_() == 4


def test_single_input() -> None:
    line = 'count'
    objs = [drgn.Object(MOCK_PROGRAM, 'void *', value=0)]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 1


def test_multiple_inputs() -> None:
    line = 'count'
    objs = [
        drgn.Object(MOCK_PROGRAM, 'void *', value=0),
        drgn.Object(MOCK_PROGRAM, 'int', value=0xfffff),
        drgn.Object(MOCK_PROGRAM, 'unsigned long *', value=0xdeadbeef),
    ]

    ret = invoke(MOCK_PROGRAM, objs, line)

    assert len(ret) == 1
    assert ret[0].value_() == 3
