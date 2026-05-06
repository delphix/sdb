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
External command loading for sdb.

This module provides the ability to load sdb commands from arbitrary
filesystem paths -- individual .py files or directories of them. Commands
are standard sdb.Command subclasses; the existing __init_subclass__
auto-registration mechanism handles the rest.

Typical usage from the library API::

    sdb.load_external_commands("/path/to/my/commands")

Or from the REPL::

    sdb> %load-commands /path/to/my/commands
"""

import glob
import importlib.util
import os
import sys
from typing import List, Set, Type


def _import_file(filepath: str) -> None:
    """Import a single Python file by absolute path."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    module_name = f"sdb_ext.{basename}"

    counter = 0
    unique_name = module_name
    while unique_name in sys.modules:
        counter += 1
        unique_name = f"{module_name}_{counter}"
    module_name = unique_name

    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {filepath}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


def load_external_commands(path: str) -> List[str]:
    """
    Load sdb Command subclasses from an external file or directory.

    If *path* is a ``.py`` file it is imported directly.  If *path* is a
    directory every ``.py`` file under it (recursively) is imported.
    Importing triggers ``Command.__init_subclass__`` which adds each new
    command to ``all_commands``.

    Returns:
        A list of command names that were newly discovered.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ImportError: If a module fails to load.
    """
    from sdb.command import Command, all_commands

    before: Set[Type[Command]] = set(all_commands)

    if not os.path.exists(path):
        raise FileNotFoundError(f"command path does not exist: {path}")

    if os.path.isfile(path) and path.endswith(".py"):
        _import_file(path)
    elif os.path.isdir(path):
        for py_file in sorted(
                glob.glob(os.path.join(path, "**", "*.py"), recursive=True)):
            if os.path.basename(py_file).startswith("__"):
                continue
            _import_file(py_file)
    else:
        raise ValueError(f"path must be a .py file or a directory, got: {path}")

    new_commands = all_commands - before
    return [name for cls in new_commands for name in cls.names]
