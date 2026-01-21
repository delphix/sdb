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
import os
import re
import sys
import zipfile

from typing import Any, Dict, List

import drgn
import sdb
from sdb.internal.repl import REPL
from sdb.mdb_compat import set_mdb_compat_enabled
from sdb.session import get_trace_manager, TraceManager

try:
    from sdb._version import version, commit_id
except ImportError:
    version = "0.0.0.dev0"
    commit_id = None


def parse_arguments() -> argparse.Namespace:
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
        action="store",
        help="evaluate CMD and exit",
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

    # Session recording and replay
    session_group = parser.add_argument_group("session recording")
    session_group.add_argument(
        "--record",
        metavar="FILE",
        type=str,
        help="record session to FILE.sdb (memory accesses, objects, symbols)",
    )
    session_group.add_argument(
        "--replay",
        metavar="FILE",
        type=str,
        help="replay a recorded session from FILE.sdb",
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


def _get_kernel_text_address(metadata: Dict[str, Any]) -> int:
    """
    Get the recorded kernel _text address from metadata.

    Priority: kernel_text_address > kernel_stext_address > 0
    """
    if 'kernel_text_address' in metadata:
        return int(metadata['kernel_text_address'])
    if 'kernel_stext_address' in metadata:
        return int(metadata['kernel_stext_address'])
    return 0


def _print_replay_info(metadata: Dict[str, Any], kernel_text: int) -> None:
    """Print replay metadata info to stderr."""
    if kernel_text != 0:
        print(f"sdb: kernel _text at {hex(kernel_text)}", file=sys.stderr)
    if 'kernel_release' in metadata:
        print(f"sdb: kernel release: {metadata['kernel_release']}",
              file=sys.stderr)
    if 'kernel_build_id' in metadata:
        print(f"sdb: expected build ID: {metadata['kernel_build_id']}",
              file=sys.stderr)


class _ReplayDebugLoader:
    """Helper class for loading debug info in replay mode."""

    def __init__(self, prog: drgn.Program, kernel_text_addr: int, quiet: bool):
        self.prog = prog
        self.kernel_text_addr = kernel_text_addr
        self.quiet = quiet
        self.module_id = 0

    def load_file(self, path: str, name: str, is_vmlinux: bool = False) -> bool:
        """
        Load a single debug file.

        For vmlinux, sets address_ranges to the recorded kernel _text address
        so drgn can calculate the correct KASLR bias.
        For modules (.ko), we skip address_ranges since we don't track
        individual module load addresses.
        """
        try:
            extra_mod = self.prog.extra_module(name,
                                               self.module_id,
                                               create=True)

            # Only set address_ranges for vmlinux (for KASLR handling)
            # Kernel modules would need their own recorded load addresses
            if is_vmlinux and self.kernel_text_addr > 0:
                kernel_size = 0x40000000  # 1GB - covers typical kernel size
                extra_mod.address_ranges = [
                    (self.kernel_text_addr, self.kernel_text_addr + kernel_size)
                ]

            extra_mod.try_file(path, force=True)
            self.module_id += 1
            return True
        except (OSError, ValueError) as e:
            if self.quiet is False:
                print(f"sdb: warning: failed to load {path}: {e}",
                      file=sys.stderr)
            return False

    def load_directory(self, dirpath: str) -> None:
        """Load all debug files from a directory.

        Note: Kernel modules (.ko) are skipped because we don't record
        their individual load addresses. Only vmlinux debug files are
        loaded when walking directories.
        """
        for ppath, __, files in os.walk(dirpath):
            for fname in files:
                # Only load vmlinux files from directories
                # .ko files need recorded module addresses to work properly
                if 'vmlinux' in fname.lower():
                    self.load_file(os.path.join(ppath, fname),
                                   fname,
                                   is_vmlinux=True)


def _load_replay_debug_info(prog: drgn.Program, dpaths: List[str], quiet: bool,
                            metadata: Dict[str, Any]) -> None:
    """
    Load debug info for replay mode using extra_module.

    In replay mode, we don't have a core dump to match modules against,
    so we use extra_module with force=True to load debug info directly.

    The key to KASLR handling: we set address_ranges to start at the
    recorded kernel_text_address. drgn then automatically calculates
    the correct debug_file_bias by comparing with the vmlinux's _text.
    """
    kernel_text = _get_kernel_text_address(metadata)

    if not quiet:
        _print_replay_info(metadata, kernel_text)

    if kernel_text == 0:
        if not quiet:
            print(
                "sdb: warning: no kernel_text_address in recording, "
                "symbols may not resolve correctly",
                file=sys.stderr)

    loader = _ReplayDebugLoader(prog, kernel_text, quiet)
    for path in dpaths:
        if os.path.isfile(path):
            basename = os.path.basename(path)
            is_vmlinux = 'vmlinux' in basename.lower()
            loader.load_file(path, basename, is_vmlinux=is_vmlinux)
        elif os.path.isdir(path):
            loader.load_directory(path)


def setup_replay_target(replay_path: str, symbol_search: List[str],
                        quiet: bool) -> drgn.Program:
    """
    Setup a drgn.Program for replay mode from a recorded session bundle.

    The bundle provides memory contents, while debug info must still be
    loaded from the original vmlinux/modules (specified via -s).
    """
    # Load the bundle
    trace_mgr = get_trace_manager()
    try:
        # Load the bundle into the trace manager
        loaded_mgr = TraceManager.load_bundle(replay_path)
        # Copy state to global manager
        trace_mgr.is_replay = True
        trace_mgr.memory = loaded_mgr.memory
        trace_mgr.objects = loaded_mgr.objects
        trace_mgr.symbols = loaded_mgr.symbols
        trace_mgr.threads = loaded_mgr.threads
        trace_mgr.metadata = loaded_mgr.metadata
    except FileNotFoundError:
        print(f"sdb: no such file: '{replay_path}'")
        sys.exit(2)
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        print(f"sdb: failed to load replay bundle: {e}")
        sys.exit(1)

    # Set up platform from metadata
    metadata = trace_mgr.metadata
    arch_name = metadata.get('arch', 'unknown')
    flags_value = metadata.get('flags', 0)

    # Create the program with platform if available
    platform = None
    if arch_name != 'unknown':
        try:
            arch = getattr(drgn.Architecture, arch_name)
            flags = drgn.PlatformFlags(flags_value)
            platform = drgn.Platform(arch, flags)
        except (AttributeError, ValueError) as e:
            if not quiet:
                print(
                    f"sdb: warning: could not create platform from metadata: {e}",
                    file=sys.stderr)

    if platform:
        prog = drgn.Program(platform)
    else:
        # Default to x86_64 Linux for kernel debugging
        prog = drgn.Program(drgn.Platform(drgn.Architecture.X86_64))

    # Load debug info using extra_module (works without a core dump)
    if symbol_search:
        _load_replay_debug_info(prog, symbol_search, quiet, metadata)

    # Set up the memory reader
    def memory_reader(address: int, count: int, _offset: int,
                      _physical: bool) -> bytes:
        return trace_mgr.memory.read(address, count)

    # Register for the full address space
    prog.add_memory_segment(0, 0xFFFFFFFFFFFFFFFF, memory_reader)

    return prog


def _run_replay_mode(args: argparse.Namespace) -> None:
    """Handle replay mode execution."""
    try:
        prog = setup_replay_target(args.replay, args.symbol_search, args.quiet)
    except PermissionError as err:
        print("sdb: " + str(err))
        return

    sdb.target.set_prog(prog)
    # In replay mode, we don't have real threads
    # Set a dummy thread value
    sdb.target.set_thread(0)
    sdb.target.set_frame(-1)
    sdb.register_commands()

    if not args.quiet:
        trace_mgr = get_trace_manager()
        status = trace_mgr.get_status()
        print(f"Replay mode: loaded {status['memory_size']} bytes "
              f"in {status['memory_segments']} segments")

    repl = REPL(prog, list(sdb.get_registered_commands().keys()))
    repl.enable_history(os.getenv("SDB_HISTORY_FILE", "~/.sdb_history"))
    if args.eval:
        exit_code = repl.eval_cmd(args.eval)
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
    sdb.register_commands()

    # Handle recording mode
    if args.record:
        trace_mgr = get_trace_manager()
        trace_mgr.start_recording(prog, args.record)
        if not args.quiet:
            print(f"Recording to: {args.record}")

    repl = REPL(prog, list(sdb.get_registered_commands().keys()))
    repl.enable_history(os.getenv("SDB_HISTORY_FILE", "~/.sdb_history"))

    try:
        if args.eval:
            exit_code = repl.eval_cmd(args.eval)
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

    # Handle replay mode
    if args.replay:
        _run_replay_mode(args)
        return

    # Normal mode (live or crash dump)
    _run_normal_mode(args)


if __name__ == "__main__":
    main()
