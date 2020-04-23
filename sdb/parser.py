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
"""
This module contains the logic for the tokenization and parsing
of the input given by the SDB REPL.
"""

#
# Why Roll Our Own Parser?
#
# Our grammar in its current state could be implemented with shlex() that is
# part of the standard library if we applied some workarounds to it. That said
# the code wouldn't be clean, it would be hard to add new rules (workarounds
# on top of workaroudns) and providing helpful error messages would be hard.
#
# In terms of external parsing libraries, the following ones were considered:
#   * PLY (Python Lex-Yacc)
#   * SLY (Sly Lex-Yacc)
#   * Lark
#
# PLY attempts to model traditional Lex & Yacc and it does come with a lot of
# their baggage. There is a lot of global state, that we'd either need to
# recreate (e.g. regenerate the grammar) every time an SDB command is issued,
# or alternatively we'd need to keep track of a few global objects and reset
# their metadata in both success and error code paths. The latter is not that
# bad but it can be very invasive in parts of the code base where we really
# shouldn't care about parsing. In addition, error-handling isn't great and
# there is a lot of boilerplate and magic to it.
#
# SLY is an improved version of PLY that deals with most issues of global
# state and boilerplace code. The error-handling is still not optimal but a
# lot better, optimizing for common cases. SLY would provide a reasonable
# alternative implementation to our hand-written parser but it wasn't chosen
# mainly for one reason. It tries to optimize for traditional full-fledged
# languages which results in a few workarounds given SDB's simplistic but
# quirky command language.
#
# Lark is probably the best option compared to the above in terms of features,
# ergonomics like error-handling, and clean parser code. The only drawback of
# this library in the context of SDB is that it is hard to debug incorrect
# grammars - the grammar is generally one whole string and if it is wrong the
# resuting stack traces end up showing methods in the library, not in the
# code that the consumer of the library wrote (which is what would geenrally
# happen with SLY). This is not a big deal in general but for SDB we still
# haven't finalized all the command language features (i.e. subshells or
# defining alias commands in the runtime) and our grammar isn't stable yet.
#
# Our hand-written parser below has a small implementation (less than 100
# lines of code without the comments), provides friendly error messages,
# and it falls cleanly to our existing code. As SDB's command language
# grows and gets more stable it should be easy to replace the existing
# parser with a library like Lark.
#

from enum import Enum
from typing import Iterable, List, Optional, Tuple

from sdb.error import ParserError


class ExpressionType(Enum):
    """
    The Expression types supported by the SDB parser that
    have semantic meaning. Their corresponding string values
    are only used for debugging purposes.

    Example:

        sdb> cmd0 arg0 | cmd1 arg1 "arg 2" ! shell_cmd shell_args ...
             ---------   -----------------   ========================

    Everything underlined with '-' is a CMD (e.g. SDB command) and
    '=' is a SHELL_CMD token.
    """
    CMD = "__cmd__"
    SHELL_CMD = "__shell_cmd__"


WHITESPACE = " \t"
QUOTES = '"\''
OPERATORS = "|!"
DELIMETERS = OPERATORS + QUOTES + WHITESPACE


def _next_non_whitespace(line: str, index: int) -> Optional[int]:
    """
    Return the index of the next non-whitespace character in `line`
    starting from `index` or None if there is no such character until
    the end of `line`.
    """
    for i, c in enumerate(line[index:]):
        if c not in WHITESPACE:
            return i + index
    return None


def _next_delimiter(line: str, index: int) -> Optional[int]:
    """
    Return the index of the next delimeter in `line` starting from
    `index` or None if there is no such character until the end of
    `line`. Generally used when we are in the middle of processing
    an identifier/token and want to see where it ends.
    """
    for i, c in enumerate(line[index:]):
        if c in DELIMETERS:
            return i + index
    return None


def tokenize(line: str) -> Iterable[Tuple[List[str], ExpressionType]]:
    """
    Iterates over the line passed as an input (usually from the REPL) and
    generates expressions to be evaluated by the SDB pipeline logic. The
    actual expression information vary by expression type:

    [1] CMD (e.g. SDB commands) expression contain a list of strings
        which contains the command (first string of list) and its
        arguments (the rest of the strings in the list).
    [2] A SHELL_CMD expression (e.g. basically anything after a bang !)
        is a single string that contains the whole shell command,
        including its arguments and the spaces between them.

    Example:

        sdb> cmd0 arg0 | cmd1 arg1 "arg 2" ! shell_cmd shell_args ...
             ---------   -----------------   ========================

        Returns:
            Iterable [
                 (['cmd0', 'arg0'], CMD),
                 (['cmd1', 'arg1', 'arg 2'], CMD),
                 (['shell_cmd shell_args ...'], SHELL_CMD),
            ]

    Note: The reason that we split the arguments for CMDs here is so we
    don't have to redo that work later in the Command class where we need
    to parse the arguments in argparse. Furthermore, the tokenizer here
    does a better job than doing a simple split() as it parses each string
    containing spaces as a single argument (e.g. space in "arg 2" in our
    example).
    """
    # pylint: disable=too-many-statements
    # pylint: disable=too-many-branches

    token_list: List[str] = []
    idx: Optional[int] = 0
    while True:
        idx = _next_non_whitespace(line, idx)  # type: ignore[arg-type]
        if idx is None:
            break

        c = line[idx]
        if c == '|':
            #
            # We encountered a pipe which marks the end of a CMD expression.
            # Yield the preceding token and move on to the next character.
            # Raise error if there no CMD preceeding the pipe.
            #
            if not token_list or idx == (len(line) - 1):
                raise ParserError(line, "freestanding pipe with no command",
                                  idx)
            yield token_list, ExpressionType.CMD
            token_list = []
            idx += 1
        elif c == '!':
            #
            # We encountered an exclamation point which is the start of a
            # SHELL_CMD. Look ahead just in case the user is trying to use
            # the inequality operator (!=) and warn them if they try to do
            # so. If all is good, consume everything after the bang as a
            # single token for our SHELL_CMD.
            #
            lookahead = _next_non_whitespace(line, idx + 1)
            if not lookahead:
                raise ParserError(line, "no shell command specified", idx)
            if line[lookahead] == "=":
                raise ParserError(
                    line,
                    "predicates that use != as an operator should be quoted",
                    idx)

            if token_list:
                yield token_list, ExpressionType.CMD
                token_list = []
            yield [line[lookahead:].strip()], ExpressionType.SHELL_CMD
            break
        elif c in QUOTES:
            #
            # We encountered a double or single quote that marks the beginning
            # of a string. Consume the whole string as a single token and add
            # it to  the token list of the current CMD that we are constructing.
            #
            # Note that the actual quotes enclosing the string are not part of
            # the actual token.
            #
            str_contents: List[str] = []
            str_end_idx = 0
            for str_idx, str_c in enumerate(line[idx + 1:]):
                #
                # If we encounter the same kind of quote then we have one of
                # the following scenarios:
                #
                # [A] Our string contains a quote that is being escaped, at
                #     which point, we replace the slash preceding it with
                #     the actual quote character and continue consuming the
                #     string.
                # [B] This is the end of the string, so we break out of this
                #     loop.
                #
                if str_c == c:
                    if str_contents and str_contents[-1] == '\\':
                        str_contents[-1] = c
                        continue
                    str_end_idx = str_idx
                    break
                str_contents.append(str_c)
            if str_end_idx == 0:
                raise ParserError(line, "unfinished string expression", idx)
            token_list.append(''.join(str_contents))
            idx += str_end_idx + 2  # + 2 added for quotes on both sides
        else:
            #
            # We found a token that is part of a CMD expression. Add
            # the token to the CMD's token list and then move on to
            # the next one character or break if we've hit the end
            # of the input line.
            #
            lookahead = _next_delimiter(line, idx)
            if not lookahead:
                token_list.append(line[idx:])
                break
            token_list.append(line[idx:lookahead])
            idx = lookahead

    if token_list:
        yield token_list, ExpressionType.CMD
        token_list = []
