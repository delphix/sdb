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

# Version is set by setuptools_scm from git tags
try:
    from sdb._version import version as __version__
except ImportError:
    __version__ = "0.0.0.dev0"

#
# We are being very explicit of what this module exposes
# so as to avoid any future cyclic-dependencies in how
# the modules are imported and attempt to have a cleaner
# separation of concerns between modules.
#
from sdb.error import (
    Error,
    CommandNotFoundError,
    CommandError,
    CommandInvalidInputError,
    SymbolNotFoundError,
    CommandArgumentsError,
    CommandEvalSyntaxError,
    ParserError,
)
from sdb.target import (
    create_object,
    get_object,
    get_prog,
    get_type,
    set_thread,
    get_thread,
    set_frame,
    get_frame,
    get_pointer_type,
    get_target_flags,
    get_symbol,
    is_null,
    type_canonical_name,
    type_canonicalize,
    type_canonicalize_name,
    type_canonicalize_size,
    type_equals,
    Runtime,
    All,
    Kernel,
    Userland,
    Module,
    Library,
)
from sdb.command import (
    Address,
    Cast,
    Command,
    InputHandler,
    Locator,
    PrettyPrinter,
    Walk,
    Walker,
    SingleInputCommand,
    get_registered_commands,
    register_commands,
)
from sdb.pipeline import execute_pipeline, get_first_type, invoke

__all__ = [
    '__version__',
    'Address',
    'All',
    'Cast',
    'Command',
    'CommandArgumentsError',
    'CommandError',
    'CommandEvalSyntaxError',
    'CommandInvalidInputError',
    'CommandNotFoundError',
    'Error',
    'InputHandler',
    'Kernel',
    'Library',
    'Locator',
    'Module',
    'ParserError',
    'PrettyPrinter',
    'Runtime',
    'SingleInputCommand',
    'SymbolNotFoundError',
    'Userland',
    'Walk',
    'Walker',
    'create_object',
    'execute_pipeline',
    'invoke',
    'is_null',
    'get_first_type',
    'get_frame',
    'get_object',
    'get_pointer_type',
    'get_prog',
    'get_registered_commands',
    'get_thread',
    'get_symbol',
    'get_target_flags',
    'get_type',
    'register_commands',
    'set_frame',
    'set_thread',
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
import sdb.commands  # noqa: F401
