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

from typing import Callable, Iterable, List, Optional

import drgn

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
from sdb.loader import load_external_commands
from sdb.pipeline import execute_pipeline, get_first_type, invoke

#
# Exit codes returned by sdb's CLI (via -e) and REPL.eval_cmd().
# Agents and scripts should use these constants to interpret results.
#
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_BAD_ARGS = 2

__all__ = [
    '__version__',
    'Address',
    'All',
    'EXIT_BAD_ARGS',
    'EXIT_ERROR',
    'EXIT_SUCCESS',
    'Cast',
    'Command',
    'CommandArgumentsError',
    'CommandError',
    'CommandEvalSyntaxError',
    'CommandInvalidInputError',
    'CommandNotFoundError',
    'connect',
    'Error',
    'InputHandler',
    'Kernel',
    'Library',
    'load_external_commands',
    'Locator',
    'Module',
    'ParserError',
    'PrettyPrinter',
    'run',
    'Runtime',
    'SingleInputCommand',
    'start',
    'SymbolNotFoundError',
    'Userland',
    'Walk',
    'Walker',
    'create_object',
    'execute_pipeline',
    'invoke',
    'is_null',
    'open_dump',
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
import sdb.commands  # noqa: F401,E402  # pylint: disable=wrong-import-position


def start(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    prog: drgn.Program,
    command_paths: Optional[List[str]] = None,
    prompt: str = "sdb> ",
    pre_cmd_hook: Optional[Callable[[], None]] = None,
    eval_cmd: Optional[str] = None,
    history_file: str = "~/.sdb_history",
) -> None:
    """
    High-level entry point for using sdb as a library.

    This function accepts a pre-configured ``drgn.Program`` (e.g. one
    created by GhostWire with TCP-backed memory segments) and starts
    the sdb REPL.  It is the primary integration point for external
    tools that want to drive sdb programmatically.

    Args:
        prog: A fully-initialised drgn.Program.
        command_paths: Optional list of filesystem paths (files or
            directories) from which to load additional sdb commands.
        prompt: REPL prompt string (or an object whose ``__str__``
            is called each time the prompt is displayed).
        pre_cmd_hook: Optional callable invoked before every command
            evaluation (e.g. to bump a transport cache generation).
        eval_cmd: If provided, evaluate this single command and return
            instead of starting the interactive REPL.
        history_file: Path used for readline history persistence.
    """
    _start_impl(prog, command_paths, prompt, pre_cmd_hook, eval_cmd,
                history_file)


def _start_impl(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    prog: drgn.Program,
    command_paths: Optional[List[str]],
    prompt: str,
    pre_cmd_hook: Optional[Callable[[], None]],
    eval_cmd: Optional[str],
    history_file: str,
) -> None:
    import os
    import sys

    import sdb.target as sdb_target
    from sdb.internal.repl import REPL
    from sdb.mdb_compat import set_mdb_compat_enabled

    set_mdb_compat_enabled(True)

    sdb_target.set_prog(prog)

    try:
        sdb_target.set_thread(prog.crashed_thread().object)
    except (ValueError, StopIteration):
        try:
            sdb_target.set_thread(next(prog.threads()).object)
        except StopIteration:
            sdb_target.set_thread(0)
    sdb_target.set_frame(-1)

    if command_paths:
        for path in command_paths:
            load_external_commands(path)

    env_paths = os.environ.get("SDB_COMMANDS_PATH", "")
    if env_paths:
        for p in env_paths.split(":"):
            if p.strip():
                load_external_commands(p.strip())

    register_commands()

    repl = REPL(prog,
                list(get_registered_commands().keys()),
                prompt=prompt,
                pre_cmd_hook=pre_cmd_hook)
    repl.enable_history(os.getenv("SDB_HISTORY_FILE", history_file))

    if eval_cmd:
        exit_code = repl.eval_cmd(eval_cmd)
        sys.exit(exit_code)
    else:
        repl.start_session()


def connect(  # pylint: disable=import-outside-toplevel
    prog: drgn.Program,
    command_paths: Optional[List[str]] = None,
) -> drgn.Program:
    """
    Set up the sdb runtime for programmatic use without starting a REPL.

    This is the recommended entry point for scripts, notebooks, and
    AI agents that want to call :func:`sdb.run` or :func:`sdb.invoke`
    without an interactive session.

    Args:
        prog: A fully initialised ``drgn.Program``.
        command_paths: Optional list of filesystem paths (files or
            directories) from which to load additional sdb commands.

    Returns:
        The same ``prog`` that was passed in (for chaining convenience).

    Example::

        import drgn, sdb

        prog = drgn.Program()
        prog.set_core_dump("vmcore")
        prog.load_debug_info(["vmlinux"])

        sdb.connect(prog)
        for obj in sdb.run("spa | member spa_name"):
            print(obj.string_().decode())
    """
    import os

    import sdb.target as sdb_target
    from sdb.mdb_compat import set_mdb_compat_enabled

    set_mdb_compat_enabled(True)
    sdb_target.set_prog(prog)

    try:
        sdb_target.set_thread(prog.crashed_thread().object)
    except (ValueError, StopIteration, Exception):  # pylint: disable=broad-exception-caught
        try:
            sdb_target.set_thread(next(prog.threads()).object)
        except (StopIteration, Exception):  # pylint: disable=broad-exception-caught
            sdb_target.set_thread(0)
    sdb_target.set_frame(-1)

    if command_paths:
        for path in command_paths:
            load_external_commands(path)

    env_paths = os.environ.get("SDB_COMMANDS_PATH", "")
    if env_paths:
        for p in env_paths.split(":"):
            if p.strip():
                load_external_commands(p.strip())

    register_commands()
    return prog


def run(
    cmd: str,
    input_objs: Optional[Iterable[drgn.Object]] = None,
) -> List[drgn.Object]:
    """
    Execute an sdb pipeline and return results as a Python list.

    This is the primary programmatic API for running sdb commands.
    Unlike :func:`sdb.invoke` (which returns a lazy generator),
    ``run()`` eagerly evaluates the pipeline and returns a concrete
    list of ``drgn.Object`` values.

    The sdb runtime must be initialised first via :func:`sdb.connect`
    or :func:`sdb.start`.

    Args:
        cmd: An sdb pipeline string, e.g. ``"spa | member spa_name"``.
        input_objs: Optional input objects to feed into the pipeline.
            Defaults to ``[]`` (start from scratch).

    Returns:
        A list of ``drgn.Object`` results from the pipeline.

    Raises:
        sdb.Error: If the pipeline encounters a command error.
        sdb.CommandNotFoundError: If a command in the pipeline is unknown.
        sdb.CommandArgumentsError: If a command receives invalid arguments.

    Example::

        import sdb

        # After sdb.connect(prog):
        tasks = sdb.run("threads")
        print(f"Found {len(tasks)} threads")

        names = sdb.run("threads | member comm")
        for name in names:
            print(name.string_().decode())
    """
    if input_objs is None:
        input_objs = []
    return list(invoke(input_objs, cmd))


def open_dump(  # pylint: disable=too-many-locals,import-outside-toplevel
    object_file: str,
    core_file: str,
    symbol_search: Optional[List[str]] = None,
    command_paths: Optional[List[str]] = None,
    quiet: bool = False,
) -> drgn.Program:
    """
    Open a crash/core dump for programmatic analysis in one call.

    This is a convenience wrapper that creates a ``drgn.Program``, loads
    the core dump and debug info, and initialises the sdb runtime via
    :func:`sdb.connect`.  After calling this function you can immediately
    use :func:`sdb.run` and :func:`sdb.invoke`.

    Args:
        object_file: Path to the namelist (``vmlinux`` or userland binary).
        core_file: Path to the crash dump or core dump file.
        symbol_search: Optional list of additional paths to search for
            debug info (``.ko``, ``.debug``, shared objects).
        command_paths: Optional list of filesystem paths from which to
            load additional sdb commands.
        quiet: If ``True``, suppress warnings about missing debug info.

    Returns:
        The initialised ``drgn.Program``.

    Raises:
        FileNotFoundError: If *object_file* or *core_file* does not exist.

    Example::

        import sdb

        prog = sdb.open_dump("vmlinux", "vmcore")
        pools = sdb.run("spa | member spa_name")
        for p in pools:
            print(p.string_().decode())
    """
    import os
    import re
    import sys

    if not os.path.isfile(core_file):
        raise FileNotFoundError(f"core file not found: {core_file}")
    if not os.path.isfile(object_file):
        raise FileNotFoundError(f"object file not found: {object_file}")

    prog = drgn.Program()
    prog.set_core_dump(core_file)

    # Load the namelist (vmlinux / binary)
    all_symbol_paths = [object_file] + (symbol_search or [])
    for path in all_symbol_paths:
        if os.path.isfile(path):
            try:
                prog.load_debug_info([path])
            except drgn.MissingDebugInfoError as err:
                if not quiet:
                    print(f"sdb: {err}", file=sys.stderr)
        elif os.path.isdir(path):
            kos = []
            for ppath, __, files in os.walk(path):
                for fname in files:
                    if (fname.endswith(".ko") or fname.endswith(".debug") or
                            re.match(r".+\.so(\.\d)?", fname)):
                        kos.append(os.path.join(ppath, fname))
            try:
                prog.load_debug_info(kos)
            except drgn.MissingDebugInfoError as err:
                if not quiet:
                    print(f"sdb: {err}", file=sys.stderr)

    return connect(prog, command_paths=command_paths)
