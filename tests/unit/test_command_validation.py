#
# Copyright 2025 CoreWeave
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

import pytest

from sdb.command import is_valid_command_name

# Valid command names (follow C identifier rules)
VALID_COMMAND_NAMES = [
    # Simple names
    "spa",
    "print",
    "echo",
    "head",
    "tail",

    # Names with underscores
    "zfs_histogram",
    "spl_kmem_caches",
    "spa_namespace_avl",
    "_internal",
    "_",
    "__private",

    # Names with digits (not at start)
    "Cmd1",
    "v2",
    "test123",
    "cmd_v2_final",

    # Mixed case
    "MyCommand",
    "camelCase",
    "UPPERCASE",
]

# Invalid command names (don't follow C identifier rules)
INVALID_COMMAND_NAMES = [
    # Starting with colon (conflicts with mdb syntax)
    ":colon",
    "::double_colon",
    "::",

    # Starting with other special characters
    ";semicolon",
    ",comma",
    ".dot",
    "/slash",
    "%percent",
    "@at",
    "$dollar",
    "#hash",
    "!bang",
    "&ampersand",
    "*asterisk",
    "(paren",
    ")paren",
    "[bracket",
    "]bracket",
    "{brace",
    "}brace",
    "<less",
    ">greater",
    "=equals",
    "+plus",
    "-minus",
    "|pipe",
    "\\backslash",
    "\"quote",
    "'apostrophe",
    "`backtick",
    "~tilde",
    "^caret",

    # Starting with digits
    "1digit",
    "123cmd",
    "0x1234",

    # Containing special characters in the middle
    "spa::print",
    "foo.bar",
    "foo-bar",
    "foo/bar",
    "foo bar",

    # Empty string
    "",
]


@pytest.mark.parametrize('name', VALID_COMMAND_NAMES)
def test_valid_command_names(name: str) -> None:
    """Test that valid command names are accepted."""
    assert is_valid_command_name(name) is True


@pytest.mark.parametrize('name', INVALID_COMMAND_NAMES)
def test_invalid_command_names(name: str) -> None:
    """Test that invalid command names are rejected."""
    assert is_valid_command_name(name) is False
