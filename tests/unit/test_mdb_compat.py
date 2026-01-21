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

from sdb.mdb_compat import (preprocess_mdb_syntax, set_mdb_compat_enabled,
                            is_mdb_compat_enabled)

# Test cases for mdb syntax preprocessing
# Format: (input, expected_output)
MDB_COMPAT_POSITIVE_TABLE = [
    # Basic transformation - symbol::cmd -> addr symbol | cmd
    ("spa::print", "addr spa | print"),
    ("spa_namespace_avl::print", "addr spa_namespace_avl | print"),
    ("spa_namespace_avl::print -nr", "addr spa_namespace_avl | print -nr"),

    # Hex address transformation
    ("0xffff1234::print", "addr 0xffff1234 | print"),
    ("0xffffffffc0954fe0::print -nr", "addr 0xffffffffc0954fe0 | print -nr"),

    # With arguments after the command
    ("spa::vdev 0", "addr spa | vdev 0"),
    ("spa::member spa_root_vdev", "addr spa | member spa_root_vdev"),

    # With pipes after the transformation
    ("spa::print | head", "addr spa | print | head"),
    ("spa::print | head 5", "addr spa | print | head 5"),
    ("spa::print -nr | head 5", "addr spa | print -nr | head 5"),
    ("spa::vdev | metaslab | count", "addr spa | vdev | metaslab | count"),

    # Redundant :: after pipes (should be stripped)
    ("spa::print | ::head", "addr spa | print | head"),
    ("spa::print | ::head 5", "addr spa | print | head 5"),
    ("spa::print | ::head | ::tail", "addr spa | print | head | tail"),

    # No transformation needed (standard sdb syntax)
    ("spa | print", "spa | print"),
    ("addr spa | print", "addr spa | print"),
    ("spa rpool | vdev | head", "spa rpool | vdev | head"),
    ("echo 0x1234", "echo 0x1234"),
    ("slabs", "slabs"),
    ("slabs | head 5", "slabs | head 5"),

    # Empty and whitespace
    ("", ""),
    ("   ", "   "),

    # Preserve content inside double quotes
    ('cmd "foo::bar"', 'cmd "foo::bar"'),
    ('filter "obj.name::value"', 'filter "obj.name::value"'),
    ('echo "test::string" | head', 'echo "test::string" | head'),

    # Preserve content inside single quotes
    ("cmd 'foo::bar'", "cmd 'foo::bar'"),
    ("filter 'obj.name::value'", "filter 'obj.name::value'"),

    # Preserve shell commands after !
    ("cmd ! grep ::pattern", "cmd ! grep ::pattern"),
    ("spa::print ! grep foo", "addr spa | print ! grep foo"),
    ("spa::print | head ! grep ::test",
     "addr spa | print | head ! grep ::test"),

    # Mixed quoted and unquoted
    ('spa::print "arg::with::colons"', 'addr spa | print "arg::with::colons"'),

    # Edge cases with spacing
    ("  spa::print  ", "addr spa | print "),
    ("spa::print|head", "addr spa | print|head"),
    ("spa::print |head", "addr spa | print |head"),
    ("spa::print| head", "addr spa | print| head"),

    # No double colons at all
    ("spa | vdev | metaslab", "spa | vdev | metaslab"),
    ("addr spa_namespace_avl | walk", "addr spa_namespace_avl | walk"),

    # Only :: without symbol (edge case - just strip it)
    ("::print", "print"),
]


@pytest.mark.parametrize('input_,expected', MDB_COMPAT_POSITIVE_TABLE)
def test_mdb_preprocess(input_: str, expected: str) -> None:
    """Test mdb syntax preprocessing transforms input correctly."""
    assert preprocess_mdb_syntax(input_) == expected


# Test that the preprocessing doesn't break existing functionality
PASSTHROUGH_TABLE = [
    # Standard sdb commands should pass through unchanged
    "spa",
    "spa rpool",
    "slabs | head 5",
    "addr spa_namespace_avl | walk",
    "echo 0xdeadbeef | cast void *",
    'filter "obj.value > 0"',
    "threads | stacks",
    "zfs_dbgmsg | head 10",
]


@pytest.mark.parametrize('input_', PASSTHROUGH_TABLE)
def test_mdb_preprocess_passthrough(input_: str) -> None:
    """Test that standard sdb syntax passes through unchanged."""
    assert preprocess_mdb_syntax(input_) == input_


# Edge cases and potential error scenarios
# These test what the preprocessor produces for unusual inputs.
# Note: The preprocessor doesn't validate commands - that happens later
# in the pipeline. These tests document the expected transformation behavior.
MDB_COMPAT_EDGE_CASES = [
    # Multiple :: in first segment - only first :: is processed
    # This produces 'addr spa | print::head' which will fail later as
    # 'print::head' is not a valid command (command not found error)
    ("spa::print::head", "addr spa | print::head"),

    # Triple colon - treated as :: followed by :
    # Produces 'addr arg | :cmd' - ':cmd' would fail command name validation
    ("arg:::cmd", "addr arg | :cmd"),

    # Quadruple colon - treated as two ::
    # Produces 'addr arg | ::cmd' which then has :: in a non-first segment
    # but since it's not after a pipe separator, it stays as is
    ("arg::::cmd", "addr arg | ::cmd"),

    # Empty symbol (just ::cmd at start)
    ("::print", "print"),
    ("::print -nr", "print -nr"),

    # :: at the end (no command after)
    ("spa::", "addr spa | "),

    # Only ::
    ("::", ""),

    # Multiple segments with multiple ::
    ("spa::print::foo | head", "addr spa | print::foo | head"),

    # :: in middle segment (not first, not after pipe with leading ::)
    ("cmd | spa::print | head", "cmd | spa::print | head"),

    # Whitespace around ::
    # Space before :: - still transformed, symbol includes trailing space
    ("spa ::print", "addr spa  | print"),
    # Space after :: gets stripped by lstrip()
    ("spa:: print", "addr spa | print"),

    # Numbers that look like addresses
    ("0x0::print", "addr 0x0 | print"),
    ("0::print", "addr 0 | print"),
    ("123::print", "addr 123 | print"),

    # Special characters in symbol (will transform, command lookup will fail)
    ("foo-bar::print", "addr foo-bar | print"),
    ("foo.bar::print", "addr foo.bar | print"),
]


@pytest.mark.parametrize('input_,expected', MDB_COMPAT_EDGE_CASES)
def test_mdb_preprocess_edge_cases(input_: str, expected: str) -> None:
    """
    Test edge cases and unusual inputs.

    These document what the preprocessor produces for unusual patterns.
    Invalid commands (like ':cmd' or 'print::head') will be caught later
    in the pipeline by command lookup or command name validation.
    """
    assert preprocess_mdb_syntax(input_) == expected


# Test that the enable/disable flag works
def test_mdb_compat_disabled() -> None:
    """Test that preprocessing can be disabled."""
    # Save original state
    original = is_mdb_compat_enabled()

    try:
        # Disable preprocessing
        set_mdb_compat_enabled(False)
        assert is_mdb_compat_enabled() is False

        # Input should pass through unchanged when disabled
        assert preprocess_mdb_syntax("spa::print") == "spa::print"
        assert preprocess_mdb_syntax("spa::print | head") == "spa::print | head"

        # Re-enable preprocessing
        set_mdb_compat_enabled(True)
        assert is_mdb_compat_enabled() is True

        # Should transform again
        assert preprocess_mdb_syntax("spa::print") == "addr spa | print"
    finally:
        # Restore original state
        set_mdb_compat_enabled(original)
