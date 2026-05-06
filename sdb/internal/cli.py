#
# Copyright 2019 Delphix
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
This file contains all the logic of the sdb "executable"
like the entry point, command line interface, etc...
"""

import argparse
import inspect
import json
import os
import re
import sys

from typing import Any, Dict, List, Set, Type

import drgn
import sdb
from sdb.internal.repl import REPL
from sdb.mdb_compat import set_mdb_compat_enabled
from sdb.session import get_trace_manager, extract_sdb_notes

try:
    from sdb._version import version, commit_id
except ImportError:
    version = "0.0.0.dev0"
    commit_id = None


def parse_arguments() -> argparse.Namespace:  # pylint: disable=too-many-branches
    """
    Sets up argument parsing and does the first pass of validation
    of the command line input.
    """
    parser = argparse.ArgumentParser(prog="sdb",
                                     description="The Slick/Simple Debugger")

    version_string = f"sdb {version}"
    if commit_id:
        version_string += f" ({commit_id})"
    parser.add_argument("-V",
                        "--version",
                        action="version",
                        version=version_string)

    dump_group = parser.add_argument_group("core/crash dump analysis")
    dump_group.add_argument(
        "object",
        nargs="?",
        default="",
        help="a namelist like vmlinux or userland binary",
    )
    dump_group.add_argument("core",
                            nargs="?",
                            default="",
                            help="the core/crash dump to be debugged")

    live_group = parser.add_argument_group(
        "live system analysis").add_mutually_exclusive_group()
    live_group.add_argument("-k",
                            "--kernel",
                            action="store_true",
                            help="debug the running kernel (default)")
    live_group.add_argument(
        "-p",
        "--pid",
        metavar="PID",
        type=int,
        help="debug the running process of the specified PID",
    )

    dis_group = parser.add_argument_group("debug info and symbols")
    dis_group.add_argument(
        "-s",
        "--symbol-search",
        metavar="PATH",
        default=[],
        action="append",
        help="load debug info and symbols from the given directory or file;" +
        " this may option may be given more than once",
    )
    dis_group.add_argument(
        "-A",
        "--no-default-symbols",
        dest="default_symbols",
        action="store_false",
        help=
        "don't load any debugging symbols that were not explicitly added with -s",
    )

    parser.add_argument(
        "-e",
        "--eval",
        metavar="CMD",
        type=str,
        action="append",
        default=[],
        help="evaluate CMD and exit; may be given more than once"
        " to run multiple commands in sequence",
    )
    parser.add_argument(
        "-",
        dest="stdin_script",
        action="store_true",
        help="read commands from stdin (one per line) and exit",
    )
    parser.add_argument("-q",
                        "--quiet",
                        action="store_true",
                        help="don't print non-fatal warnings")
    parser.add_argument(
        "--no-mdb-compat",
        dest="mdb_compat",
        action="store_false",
        help="disable mdb compatibility syntax (symbol::cmd)",
    )
    parser.add_argument(
        "--load-commands",
        metavar="PATH",
        default=[],
        action="append",
        help="load external sdb commands from PATH (file or directory);"
        " this option may be given more than once",
    )

    # AI agent / tooling integration
    agent_group = parser.add_argument_group("agent and tooling integration")
    agent_group.add_argument(
        "--list-commands",
        action="store_true",
        help="list all available commands as JSON and exit"
        " (does not require a target)",
    )
    agent_group.add_argument(
        "--json",
        action="store_true",
        help="emit pipeline output as JSON (use with -e)",
    )

    # Session recording and replay
    session_group = parser.add_argument_group("session recording")
    session_group.add_argument(
        "--record",
        metavar="FILE",
        type=str,
        help="record session to FILE.vmcore.recorded (standard vmcore format)",
    )
    session_group.add_argument(
        "--replay",
        metavar="FILE",
        type=str,
        help="replay a recorded session from a .vmcore.recorded file",
    )

    args = parser.parse_args()

    #
    # If an 'object' (and maybe 'core') parameter has been specified
    # we are analyzing a core dump or a crash dump. With that in mind
    # it is harder to user argparse to make the above two mutually
    # exclusive with '-k' or '-p PID' which are for analyzing live
    # targets. As a result we enforce this mutual exclusions on our
    # own below. Unfortunately this is still not close to ideal as
    # the help message will show something like this:
    # ```
    # usage: sdb [-h] [-k | -p PID] [-d PATH] ... [object] [core]
    # ```
    # instead of:
    # ```
    # usage: sdb [-h] [-k | -p PID | object core] [-d PATH] ...
    # ```
    #
    if args.object and args.kernel:
        parser.error(
            "cannot specify an object file while also specifying --kernel")
    if args.object and args.pid:
        parser.error(
            "cannot specify an object file while also specifying --pid")

    #
    # We currently cannot handle object files without cores.
    #
    if args.object and not args.core:
        parser.error("raw object file target is not supported yet")

    #
    # Replay mode is mutually exclusive with other target options
    #
    if args.replay:
        if args.object or args.core:
            parser.error("cannot specify object/core files with --replay")
        if args.kernel:
            parser.error("cannot specify --kernel with --replay")
        if args.pid:
            parser.error("cannot specify --pid with --replay")

    #
    # Recording requires a target (can't record nothing)
    #
    if args.record and args.replay:
        parser.error("cannot use --record and --replay together")

    #
    # --json requires -e or stdin mode (non-interactive mode)
    #
    if args.json and not args.eval and not args.stdin_script:
        parser.error("--json requires -e/--eval or -")

    #
    # --list-commands is standalone and doesn't need a target
    #
    if args.list_commands:
        if args.object or args.core or args.kernel or args.pid:
            parser.error("--list-commands cannot be combined with a target")
        if args.replay:
            parser.error("--list-commands cannot be combined with --replay")

    return args


def load_debug_info(prog: drgn.Program, dpaths: List[str], quiet: bool,
                    no_filter: bool) -> None:
    """
    Iterates over all the paths provided (`dpaths`) and attempts
    to load any debug information it finds. If the path provided
    is a directory, the whole directory is traversed in search
    of debug info.
    """
    for path in dpaths:
        if os.path.isfile(path):
            prog.load_debug_info([path])
        elif os.path.isdir(path):
            kos = []
            for ppath, __, files in os.walk(path):
                for i in files:
                    if (i.endswith(".ko") or i.endswith(".debug") or
                            re.match(r".+\.so(\.\d)?", i) or no_filter):
                        # matches:
                        #     kernel modules - .ko suffix
                        #     userland debug files - .debug suffix
                        #     userland shared objects - .so suffix
                        kos.append(os.sep.join([ppath, i]))
            try:
                prog.load_debug_info(kos)
            except drgn.MissingDebugInfoError as debug_info_err:
                #
                # If we encounter such an error it means that we can't
                # find the debug info for one or more kernel modules.
                # That's fine because the user may not need those, so
                # print a warning and proceed.
                #
                # Again because of the aforementioned short-coming of drgn
                # we quiet any errors when loading the *default debug info*
                # if we are looking at a crash/core dump.
                #
                if not quiet:
                    print("sdb: " + str(debug_info_err), file=sys.stderr)
        else:
            print("sdb: " + path + " is not a regular file or directory")


def setup_target(args: argparse.Namespace) -> drgn.Program:
    """
    Based on the validated input from the command line, setup the
    drgn.Program for our target and its metadata.
    """
    prog = drgn.Program()
    if args.core:
        try:
            prog.set_core_dump(args.core)
        except FileNotFoundError:
            print(f"sdb: no such file: '{args.core}'")
            sys.exit(2)

        #
        # This is currently a short-coming of drgn. Whenever we
        # open a crash/core dump we need to specify the vmlinux
        # or userland binary using the non-default debug info
        # load API.
        #
        args.symbol_search = [args.object] + args.symbol_search
    elif args.pid:
        prog.set_pid(args.pid)
    else:
        prog.set_kernel()

    if args.default_symbols:
        try:
            prog.load_default_debug_info()
        except drgn.MissingDebugInfoError as debug_info_err:
            #
            # If we encounter such an error it means that we can't
            # find the debug info for one or more kernel modules.
            # That's fine because the user may not need those, so
            # print a warning and proceed.
            #
            # Again because of the aforementioned short-coming of drgn
            # we quiet any errors when loading the *default debug info*
            # if we are looking at a crash/core dump.
            #
            if not args.quiet and not args.object:
                print("sdb: " + str(debug_info_err), file=sys.stderr)

    if args.symbol_search:
        try:
            load_debug_info(prog, args.symbol_search, args.quiet, False)
        except (
                drgn.MissingDebugInfoError,
                OSError,
        ) as debug_info_err:
            #
            # See similar comment above
            #
            if not args.quiet:
                print("sdb: " + str(debug_info_err), file=sys.stderr)

    return prog


def setup_replay_target(replay_path: str, symbol_search: List[str],
                        quiet: bool) -> drgn.Program:
    """
    Setup a drgn.Program for replay mode from a recorded vmcore.

    The vmcore is a standard ELF64 file created by kdumpling during recording.
    drgn loads it directly via set_core_dump(), no custom memory reader needed.
    """
    # Mark trace manager as replay mode
    trace_mgr = get_trace_manager()
    trace_mgr.is_replay = True

    # Extract SDB metadata from custom notes (optional)
    sdb_metadata = extract_sdb_notes(replay_path)
    if sdb_metadata:
        trace_mgr.metadata = sdb_metadata
        if not quiet and 'kernel_release' in sdb_metadata:
            print(f"sdb: recorded kernel: {sdb_metadata['kernel_release']}",
                  file=sys.stderr)

    # Create program and load the vmcore - standard drgn API
    prog = drgn.Program()
    try:
        prog.set_core_dump(replay_path)
    except FileNotFoundError:
        print(f"sdb: no such file: '{replay_path}'")
        sys.exit(2)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"sdb: failed to load vmcore: {e}")
        sys.exit(1)

    # Load debug info from symbol search paths
    if symbol_search:
        load_debug_info(prog, symbol_search, quiet, False)

    return prog


def _load_external_command_paths(args: argparse.Namespace, quiet: bool) -> None:
    """Load external commands from --load-commands flags and SDB_COMMANDS_PATH."""
    from sdb.loader import load_external_commands

    paths = list(args.load_commands)

    env_paths = os.environ.get("SDB_COMMANDS_PATH", "")
    if env_paths:
        for p in env_paths.split(":"):
            if p.strip():
                paths.append(p.strip())

    for path in paths:
        try:
            new_names = load_external_commands(path)
            if not quiet and new_names:
                print(f"sdb: loaded {len(new_names)} command(s) from {path}",
                      file=sys.stderr)
        except (FileNotFoundError, ImportError, ValueError) as e:
            print(f"sdb: warning: {e}", file=sys.stderr)


def _get_command_type_name(cls: type) -> str:
    """Return a human-readable type string for a command class."""
    types = []
    if issubclass(cls, sdb.Locator):
        types.append("Locator")
    if issubclass(cls, sdb.PrettyPrinter):
        types.append("PrettyPrinter")
    if issubclass(cls, sdb.Walker):
        types.append("Walker")
    if issubclass(cls, sdb.SingleInputCommand):
        types.append("SingleInputCommand")
    if not types:
        types.append("Command")
    return "+".join(types)


def _get_command_summary(cls: type) -> str:
    """Extract the first line of a command's docstring."""
    if not cls.__doc__:
        return ""
    doc = inspect.getdoc(cls)
    if doc:
        return doc.splitlines()[0].strip()
    return ""


def _list_commands_json(args: argparse.Namespace) -> None:
    """
    Dump all known commands as a JSON array and exit.

    This works without a target — it imports all command modules and
    inspects the class metadata directly from `all_commands`.
    """
    _load_external_command_paths(args, quiet=True)

    # Import triggers __init_subclass__ for all built-in commands.
    # all_commands contains every Command subclass regardless of runtime.
    from sdb.command import all_commands  # pylint: disable=import-outside-toplevel

    # De-duplicate: group by class, not by alias name.
    seen_classes: Set[Type[Any]] = set()
    result = []
    for cls in sorted(all_commands, key=lambda c: c.names[0]
                      if c.names else ""):
        if cls in seen_classes or not cls.names:
            continue
        seen_classes.add(cls)

        entry: Dict[str, Any] = {
            "names": cls.names,
            "type": _get_command_type_name(cls),
            "summary": _get_command_summary(cls),
        }
        if cls.input_type is not None:
            entry["input_type"] = cls.input_type
        if hasattr(cls, "output_type") and cls.output_type is not None:
            entry["output_type"] = cls.output_type

        # Collect @InputHandler types for Locators
        if issubclass(cls, sdb.Locator):
            handler_types = []
            for _, method in inspect.getmembers(cls, inspect.isfunction):
                if hasattr(method, "input_typename_handled"):
                    handler_types.append(method.input_typename_handled)
            if handler_types:
                entry["input_handler_types"] = handler_types

        # Runtime info
        runtimes = []
        for rt in cls.load_on:
            runtimes.append(type(rt).__name__)
        if runtimes:
            entry["load_on"] = runtimes

        result.append(entry)

    json.dump(result, sys.stdout, indent=2)
    print()  # trailing newline


def _get_eval_commands(args: argparse.Namespace) -> List[str]:
    """
    Collect commands to evaluate from -e flags and/or stdin.

    Returns an empty list if neither -e nor stdin mode was requested
    (meaning we should start the interactive REPL).
    """
    cmds = list(args.eval)
    if args.stdin_script:
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith('#'):
                cmds.append(line)
    return cmds


def _eval_commands(repl: REPL, cmds: List[str]) -> int:
    """
    Evaluate a list of commands sequentially.

    Returns the worst (highest) exit code. Stops on the first
    non-zero exit code.
    """
    for cmd in cmds:
        exit_code = repl.eval_cmd(cmd)
        if exit_code != 0:
            return exit_code
    return 0


def _run_replay_mode(args: argparse.Namespace) -> None:
    """Handle replay mode execution."""
    try:
        prog = setup_replay_target(args.replay, args.symbol_search, args.quiet)
    except PermissionError as err:
        print("sdb: " + str(err))
        return

    sdb.target.set_prog(prog)

    # Try to get crashed thread, fall back to first thread or dummy
    try:
        sdb.target.set_thread(prog.crashed_thread().object)
    except ValueError:
        try:
            sdb.target.set_thread(next(prog.threads()).object)
        except StopIteration:
            sdb.target.set_thread(0)

    sdb.target.set_frame(-1)
    _load_external_command_paths(args, args.quiet)
    sdb.register_commands()

    if not args.quiet:
        print(f"Replay mode: loaded {args.replay}")

    repl = REPL(prog,
                list(sdb.get_registered_commands().keys()),
                json_mode=args.json)
    repl.enable_history(os.getenv("SDB_HISTORY_FILE", "~/.sdb_history"))
    cmds = _get_eval_commands(args)
    if cmds:
        exit_code = _eval_commands(repl, cmds)
        sys.exit(exit_code)
    else:
        repl.start_session()


def _run_normal_mode(args: argparse.Namespace) -> None:
    """Handle normal (live or crash dump) mode execution."""
    try:
        prog = setup_target(args)
    except PermissionError as err:
        print("sdb: " + str(err))
        return
    sdb.target.set_prog(prog)
    try:
        sdb.target.set_thread(prog.crashed_thread().object)
    except ValueError:
        sdb.target.set_thread(next(prog.threads()).object)
    sdb.target.set_frame(-1)
    _load_external_command_paths(args, args.quiet)
    sdb.register_commands()

    # Handle recording mode
    if args.record:
        trace_mgr = get_trace_manager()
        trace_mgr.start_recording(prog, args.record)
        if not args.quiet:
            print(f"Recording to: {args.record}")

    repl = REPL(prog,
                list(sdb.get_registered_commands().keys()),
                json_mode=args.json)
    repl.enable_history(os.getenv("SDB_HISTORY_FILE", "~/.sdb_history"))

    cmds = _get_eval_commands(args)
    try:
        if cmds:
            exit_code = _eval_commands(repl, cmds)
            # If recording, stop and save
            if args.record:
                _stop_recording_if_active(prog, args.quiet)
            sys.exit(exit_code)
        else:
            repl.start_session()
    finally:
        # If recording was active and we're exiting, save it
        if args.record:
            _stop_recording_if_active(prog, args.quiet, newline=True)


def _stop_recording_if_active(prog: drgn.Program,
                              quiet: bool,
                              newline: bool = False) -> None:
    """Stop recording if it's active and print status."""
    trace_mgr = get_trace_manager()
    if trace_mgr.is_recording:
        saved_path = trace_mgr.stop_recording(prog)
        if not quiet:
            status = trace_mgr.get_status()
            prefix = "\n" if newline else ""
            print(f"{prefix}Recording saved to: {saved_path}")
            print(f"  Memory: {status['memory_size']} bytes")


def main() -> None:
    """The entry point of the sdb "executable" """
    args = parse_arguments()

    # Configure mdb compatibility syntax preprocessing
    set_mdb_compat_enabled(args.mdb_compat)

    # --list-commands: dump command metadata as JSON and exit (no target needed)
    if args.list_commands:
        _list_commands_json(args)
        return

    # Handle replay mode
    if args.replay:
        _run_replay_mode(args)
        return

    # Normal mode (live or crash dump)
    _run_normal_mode(args)


if __name__ == "__main__":
    main()
