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
"""This module contains the "sdb.Error" exception."""


class Error(Exception):
    """
    This is the superclass of all SDB error exceptions.
    """

    text: str = ""

    def __init__(self, text: str) -> None:
        self.text = f"sdb: {text}"
        super().__init__(self.text)


class CommandNotFoundError(Error):
    # pylint: disable=missing-docstring

    command: str = ""

    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(f"cannot recognize command: {command}")


class CommandError(Error):
    # pylint: disable=missing-docstring

    command: str = ""
    message: str = ""

    def __init__(self, command: str, message: str) -> None:
        self.command = command
        self.message = message
        super().__init__(f"{command}: {message}")


class CommandInvalidInputError(CommandError):
    # pylint: disable=missing-docstring

    argument: str = ""

    def __init__(self, command: str, argument: str) -> None:
        self.argument = argument
        super().__init__(command, f"invalid input: {argument}")


class SymbolNotFoundError(CommandError):
    # pylint: disable=missing-docstring

    symbol: str = ""

    def __init__(self, command: str, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(command, f"symbol not found: {symbol}")


class CommandArgumentsError(CommandError):
    # pylint: disable=missing-docstring

    def __init__(self, command: str) -> None:
        super().__init__(command,
                         'invalid input. Use -h to get argument description')


class CommandEvalSyntaxError(CommandError):
    # pylint: disable=missing-docstring

    def __init__(self, command: str, err: SyntaxError) -> None:
        msg = f"{err.msg}:\n\t{err.text}"
        if err.offset is not None and err.text is not None:
            nspaces: int = err.offset - 1
            spaces_str = list(' ' * len(err.text))
            spaces_str[nspaces] = '^'
            indicator = ''.join(spaces_str)
            msg += f"\n\t{indicator}"
        super().__init__(command, msg)


class ParserError(Error):
    """
    Thrown when SDB fails to parse input from the user.
    """

    line: str = ""
    message: str = ""
    offset: int = 0

    def __init__(self, line: str, message: str, offset: int = 0) -> None:
        self.line, self.message, self.offset = line, message, offset
        msg = (f"syntax error: {self.message}\n"
               f"  {self.line}\n"
               f"  {' ' * (self.offset)}^")
        super().__init__(msg)
