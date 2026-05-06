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
"""
This module provides mdb compatibility syntax preprocessing for SDB.

It transforms mdb-style commands like 'symbol::cmd' into the equivalent
sdb syntax 'addr symbol | cmd'.

IMPORTANT: This module only emulates the mdb command syntax (the '::' operator
for specifying an address/symbol followed by a command). It does NOT emulate
other mdb features such as:
- Number format conversions (e.g., 0t for decimal, 0i for octal)
- Expression evaluation syntax
- Variable assignment syntax ($var=value)
- Macro definitions
- Any other mdb-specific syntax or semantics

The sole purpose is to allow users familiar with mdb to use the familiar
'address::command' pattern instead of 'addr address | command'.
"""

from typing import List, Tuple

# Global flag to enable/disable mdb syntax preprocessing
# Can be disabled via --no-mdb-compat CLI flag
_mdb_compat_enabled = True  # pylint: disable=invalid-name


def set_mdb_compat_enabled(enabled: bool) -> None:
    """Enable or disable mdb compatibility syntax preprocessing."""
    global _mdb_compat_enabled  # pylint: disable=global-statement,invalid-name
    _mdb_compat_enabled = enabled


def is_mdb_compat_enabled() -> bool:
    """Check if mdb compatibility syntax preprocessing is enabled."""
    return _mdb_compat_enabled


# Characters that indicate we're inside a quoted string
QUOTES = '"\''


def _find_unquoted_double_colon(segment: str) -> int:
    """
    Find the index of '::' in segment that is not inside quotes.
    Returns -1 if not found.
    """
    in_quote = None
    idx = 0
    while idx < len(segment) - 1:
        char = segment[idx]

        # Track quote state
        if char in QUOTES:
            if in_quote is None:
                in_quote = char
            elif in_quote == char:
                # Check for escaped quote
                if idx > 0 and segment[idx - 1] == '\\':
                    pass  # Escaped quote, ignore
                else:
                    in_quote = None
            idx += 1
            continue

        # Look for :: outside of quotes
        if in_quote is None and char == ':' and segment[idx + 1] == ':':
            return idx

        idx += 1

    return -1


def _split_on_pipes_preserving_quotes(line: str) -> List[Tuple[str, str]]:
    """
    Split the line on '|' characters that are not inside quotes.
    Returns a list of (segment, separator) tuples.
    The separator is '|' for pipes, '!' for shell commands, or '' for the last segment.
    """
    segments: List[Tuple[str, str]] = []
    current_segment: List[str] = []
    in_quote = None
    idx = 0

    while idx < len(line):
        char = line[idx]

        # Track quote state
        if char in QUOTES:
            if in_quote is None:
                in_quote = char
            elif in_quote == char:
                # Check for escaped quote
                if current_segment and current_segment[-1] == '\\':
                    pass  # Escaped quote, ignore
                else:
                    in_quote = None
            current_segment.append(char)
            idx += 1
            continue

        # Check for pipe or bang outside quotes
        if in_quote is None:
            if char == '|':
                segments.append((''.join(current_segment), '|'))
                current_segment = []
                idx += 1
                continue
            if char == '!':
                # Everything after ! is a shell command, don't process it
                segments.append((''.join(current_segment), '!'))
                current_segment = list(line[idx + 1:])
                break

        current_segment.append(char)
        idx += 1

    # Add the last segment
    segments.append((''.join(current_segment), ''))

    return segments


def preprocess_mdb_syntax(line: str) -> str:
    """
    Transform mdb-style syntax to sdb syntax.

    Rules:
    1. 'symbol::cmd args' at start → 'addr symbol | cmd args'
    2. '| ::cmd' after pipes → '| cmd' (strip redundant ::)
    3. Preserve content inside quotes
    4. Preserve content after ! (shell commands)

    Examples:
        'spa_namespace_avl::print -nr' → 'addr spa_namespace_avl | print -nr'
        'spa::print | head 5' → 'addr spa | print | head 5'
        'spa::print | ::head 5' → 'addr spa | print | head 5'
        'cmd "foo::bar"' → 'cmd "foo::bar"' (unchanged - inside quotes)
        'cmd ! grep ::pattern' → 'cmd ! grep ::pattern' (unchanged - shell cmd)

    Note: This function can be disabled via set_mdb_compat_enabled(False) or
    the --no-mdb-compat CLI flag if the preprocessing causes issues.
    """
    if not _mdb_compat_enabled:
        return line

    if not line or '::' not in line:
        return line

    # Split the line into segments separated by pipes
    segments = _split_on_pipes_preserving_quotes(line)

    result_segments: List[str] = []
    is_first = True

    for segment, separator in segments:
        # If this is a shell command segment (after !), don't process it
        if result_segments and result_segments[-1].endswith('!'):
            # This segment is a shell command, preserve as-is
            result_segments.append(segment)
            if separator:
                result_segments.append(separator)
            continue

        stripped = segment.strip()

        # For segments after a pipe, check for leading ::
        if not is_first and stripped.startswith('::'):
            # Strip the leading :: from this segment, preserving trailing whitespace
            trailing_ws = segment[len(segment.rstrip()):]
            stripped = stripped[2:].lstrip()
            segment = ' ' + stripped + trailing_ws

        # Look for :: in the segment (outside quotes)
        colon_idx = _find_unquoted_double_colon(segment.strip())

        if colon_idx != -1 and is_first:
            # This is the first segment with :: - transform it
            stripped = segment.strip()
            symbol = stripped[:colon_idx]
            rest = stripped[colon_idx + 2:]  # Skip the ::

            if symbol:
                # Transform: symbol::cmd → addr symbol | cmd
                transformed = f'addr {symbol} | {rest.lstrip()}'
                # Preserve trailing whitespace for proper spacing before next pipe
                if segment != segment.rstrip():
                    transformed += ' '
                result_segments.append(transformed)
            else:
                # Edge case: ::cmd at the very start (no symbol) - just strip ::
                result_segments.append(rest.lstrip())
        else:
            result_segments.append(segment)

        if separator:
            result_segments.append(separator)

        is_first = False

    return ''.join(result_segments)
