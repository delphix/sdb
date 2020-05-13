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
"""
Main SDB package module.

This is the high-level module of all the functionality
that is exposed by SDB. The API exposed in this module
can be used to implement commands for SDB and alternative
CLI/consumer implementations.
"""

#
# We are being very explicit of what this module exposes
# so as to avoid any future cyclic-dependencies in how
# the modules are imported and attempt to have a cleaner
# separation of concerns between modules.
#
from sdb.error import (Error, CommandNotFoundError, CommandError,
                       CommandInvalidInputError, SymbolNotFoundError,
                       CommandArgumentsError, CommandEvalSyntaxError,
                       ParserError)
from sdb.target import (create_object, get_object, get_prog, get_typed_null,
                        get_type, get_pointer_type, get_target_flags,
                        get_symbol, type_canonical_name, type_canonicalize,
                        type_canonicalize_name, type_canonicalize_size,
                        type_equals)
from sdb.command import (Address, Cast, Command, InputHandler, Locator,
                         PrettyPrinter, Walk, Walker, SingleInputCommand,
                         get_registered_commands)
from sdb.pipeline import execute_pipeline, get_first_type, invoke

__all__ = [
    'Address',
    'Cast',
    'Command',
    'CommandArgumentsError',
    'CommandError',
    'CommandEvalSyntaxError',
    'CommandInvalidInputError',
    'CommandNotFoundError',
    'Error',
    'InputHandler',
    'Locator',
    'ParserError',
    'PrettyPrinter',
    'SingleInputCommand',
    'SymbolNotFoundError',
    'Walk',
    'Walker',
    'create_object',
    'execute_pipeline',
    'invoke',
    'get_first_type',
    'get_object',
    'get_pointer_type',
    'get_prog',
    'get_registered_commands',
    'get_symbol',
    'get_target_flags',
    'get_type',
    'get_typed_null',
    'type_canonical_name',
    'type_canonicalize',
    'type_canonicalize_name',
    'type_canonicalize_size',
    'type_equals',
]

#
# The SDB commands build on top of all the SDB "infrastructure" imported
# above, so we must be sure to import all of the commands last.
#
import sdb.commands
