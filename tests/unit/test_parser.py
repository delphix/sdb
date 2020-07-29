#
# Copyright 2020 Delphix
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
# pylint: disable=not-callable

from typing import List, Tuple

import pytest

from sdb import ParserError
from sdb.parser import tokenize, ExpressionType

PARSER_POSITIVE_TABLE = [
    # single command and args
    ("spa", [(["spa"], ExpressionType.CMD)]),
    ("  spa", [(["spa"], ExpressionType.CMD)]),
    ("spa  ", [(["spa"], ExpressionType.CMD)]),
    ("spa rpool", [(["spa", "rpool"], ExpressionType.CMD)]),
    ("spa rpool tank", [(["spa", "rpool", "tank"], ExpressionType.CMD)]),

    # pipeline spaces
    ("spa | vdev", [(["spa"], ExpressionType.CMD),
                    (["vdev"], ExpressionType.CMD)]),
    ("spa |vdev", [(["spa"], ExpressionType.CMD),
                   (["vdev"], ExpressionType.CMD)]),
    ("spa| vdev", [(["spa"], ExpressionType.CMD),
                   (["vdev"], ExpressionType.CMD)]),
    ("spa|vdev", [(["spa"], ExpressionType.CMD),
                  (["vdev"], ExpressionType.CMD)]),

    # shell pipe spaces
    ("cmd ! shell_cmd", [(["cmd"], ExpressionType.CMD),
                         (["shell_cmd"], ExpressionType.SHELL_CMD)]),
    ("cmd! shell_cmd", [(["cmd"], ExpressionType.CMD),
                        (["shell_cmd"], ExpressionType.SHELL_CMD)]),
    ("cmd !shell_cmd", [(["cmd"], ExpressionType.CMD),
                        (["shell_cmd"], ExpressionType.SHELL_CMD)]),
    ("cmd!shell_cmd", [(["cmd"], ExpressionType.CMD),
                       (["shell_cmd"], ExpressionType.SHELL_CMD)]),

    # longer pipeline + shell pipeline
    ("spa rpool| vdev 0 |metaslab| count", [(["spa",
                                              "rpool"], ExpressionType.CMD),
                                            (["vdev", "0"], ExpressionType.CMD),
                                            (["metaslab"], ExpressionType.CMD),
                                            (["count"], ExpressionType.CMD)]),
    ("spa rpool| vdev 0 |metaslab| count! less", [
        (["spa", "rpool"], ExpressionType.CMD),
        (["vdev", "0"], ExpressionType.CMD), (["metaslab"], ExpressionType.CMD),
        (["count"], ExpressionType.CMD), (["less"], ExpressionType.SHELL_CMD)
    ]),
    ("spa rpool| vdev 0 |metaslab! wc | less", [
        (["spa", "rpool"], ExpressionType.CMD),
        (["vdev", "0"], ExpressionType.CMD), (["metaslab"], ExpressionType.CMD),
        (["wc | less"], ExpressionType.SHELL_CMD)
    ]),

    # quoted argument with spaces, and other special characters
    ('cmd "arg"', [(["cmd", 'arg'], ExpressionType.CMD)]),
    ('cmd "arg same_arg"', [(["cmd", 'arg same_arg'], ExpressionType.CMD)]),
    ('cmd "arg \\"same_arg\\""', [(["cmd",
                                    'arg "same_arg"'], ExpressionType.CMD)]),
    ('cmd "arg|same_arg"', [(["cmd", 'arg|same_arg'], ExpressionType.CMD)]),
    ('cmd "arg ! same_arg"', [(["cmd", 'arg ! same_arg'], ExpressionType.CMD)]),

    # existing filter cases with quoted strings
    ('cmd | filter "obj.member_flag | 0b0010"',
     [(["cmd"], ExpressionType.CMD),
      (["filter", 'obj.member_flag | 0b0010'], ExpressionType.CMD)]),
    ('cmd | filter "obj.member_int > 3"', [(["cmd"], ExpressionType.CMD),
                                           (["filter", 'obj.member_int > 3'],
                                            ExpressionType.CMD)]),
    ('cmd | filter "obj.member_int != 0"', [(["cmd"], ExpressionType.CMD),
                                            (["filter", 'obj.member_int != 0'],
                                             ExpressionType.CMD)]),
    ('cmd | filter "obj.member_str != \\"test\\""',
     [(["cmd"], ExpressionType.CMD),
      (["filter", 'obj.member_str != "test"'], ExpressionType.CMD)]),
    ('cmd | filter \'obj.member_str != "test"\'',
     [(["cmd"], ExpressionType.CMD),
      (["filter", 'obj.member_str != "test"'], ExpressionType.CMD)]),

    # extreme quote cases
    ('cmd"arg"', [(["cmd", 'arg'], ExpressionType.CMD)]),
    ('cmd"arg same_arg"', [(["cmd", 'arg same_arg'], ExpressionType.CMD)]),
    ('cmd"arg" arg2', [(["cmd", 'arg', "arg2"], ExpressionType.CMD)]),
    ('cmd arg"arg2"', [(["cmd", 'arg', 'arg2'], ExpressionType.CMD)]),
    ('cmd\'arg\'', [(["cmd", 'arg'], ExpressionType.CMD)]),
    ('cmd\'arg same_arg\'', [(["cmd", 'arg same_arg'], ExpressionType.CMD)]),
    ('cmd\'arg\' arg2', [(["cmd", 'arg', "arg2"], ExpressionType.CMD)]),
    ('cmd arg\'arg2\'', [(["cmd", 'arg', 'arg2'], ExpressionType.CMD)]),
]


@pytest.mark.parametrize(  # type: ignore[misc]
    'entry,expected', PARSER_POSITIVE_TABLE)
def test_parser(entry: str, expected: List[Tuple[List[str],
                                                 ExpressionType]]) -> None:
    assert list(tokenize(entry)) == expected


PARSER_NEGATIVE_TABLE = [
    # quote-related
    ('cmd"', "unfinished string expression"),
    ('cmd "', "unfinished string expression"),
    ('cmd"arg', "unfinished string expression"),
    ('cmd arg "', "unfinished string expression"),
    ('cmd arg "arg2', "unfinished string expression"),
    ('cmd arg "arg2 | cmd1 arg3 arg4 | cmd2', "unfinished string expression"),
    ('cmd\'', "unfinished string expression"),
    ('cmd \'', "unfinished string expression"),
    ('cmd\'arg', "unfinished string expression"),
    ('cmd arg \'', "unfinished string expression"),
    ('cmd arg \'arg2', "unfinished string expression"),
    ('cmd arg \'arg2 | cmd1 arg3 arg4 | cmd2', "unfinished string expression"),

    # pipe-related
    ("|", "freestanding pipe with no command"),
    ("cmd |", "freestanding pipe with no command"),
    ("cmd ||", "freestanding pipe with no command"),
    ("cmd || cmd2", "freestanding pipe with no command"),

    # shell-related
    ("echo !", "no shell command specified"),
    ('cmd | filter obj.member_int != 0',
     "predicates that use != as an operator should be quoted"),
]


@pytest.mark.parametrize(  # type: ignore[misc]
    'entry,expected_cause', PARSER_NEGATIVE_TABLE)
def test_parser_negative(entry: str, expected_cause: str) -> None:
    with pytest.raises(ParserError) as err:
        list(tokenize(entry))
    assert expected_cause in str(err.value)
