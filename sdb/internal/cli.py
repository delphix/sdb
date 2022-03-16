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
This file contains all the logic of the sdb "executable"
like the entry point, command line interface, etc...
"""

import argparse
import os
import sys
import string

from typing import Iterable, List

import drgn
import sdb
from sdb.internal.repl import REPL


def parse_arguments() -> argparse.Namespace:
    """
    Sets up argument parsing and does the first pass of validation
    of the command line input.
    """
    parser = argparse.ArgumentParser(prog="sdb",
                                     description="The Slick/Simple Debugger")

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

    parser.add_argument("-e",
                        "--eval",
                        metavar="CMD",
                        type=str,
                        action="store",
                        help="evaluate CMD and exit")
    parser.add_argument("-q",
                        "--quiet",
                        action="store_true",
                        help="don't print non-fatal warnings")
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

    return args


def load_debug_info(prog: drgn.Program,
                    dpaths: List[str],
                    vml: str = "") -> None:
    """
    Iterates over all the paths provided (`dpaths`) and attempts
    to load any debug information it finds. If the path provided
    is a directory, the whole directory is traversed in search
    of debug info.
    """
    if vml:
        found = False
        for target in ['/usr/lib/debug', '/root']:
            vmlinux = []
            for root, _dirs, files in os.walk(target):
                if vml in files:
                    found = True
                    vmlinux.append(os.sep.join([root, vml]))
                    print(f"sdb using {vmlinux} auto-detected from core file")
                    prog.load_debug_info(vmlinux)
                    break
            if found:
                break
    for path in dpaths:
        if os.path.isfile(path):
            prog.load_debug_info([path])
        elif os.path.isdir(path):
            kos = []
            for (ppath, __, files) in os.walk(path):
                for i in files:
                    if i.endswith(".ko"):
                        kos.append(os.sep.join([ppath, i]))
            prog.load_debug_info(kos)
        else:
            print("sdb: " + path + " is not a regular file or directory")


def strings(fname: str, minlen: int = 4, maxlen: int = 16384) -> Iterable[str]:
    """
    Generate strings of at least minlen from the binary file.
    """
    with open(fname, errors="ignore") as f:
        result = ""
        for c in f.read(maxlen):
            if c in string.printable:
                result += c
                continue
            if len(result) >= minlen:
                yield result
            result = ""
        if len(result) >= minlen:  # catch result at EOF
            yield result


def detect_from_core(core: str) -> str:
    """
    Parse through the core looking for OSRELEASE=<core>
    """
    match = "OSRELEASE"
    line = ""
    vm = ""
    for s in strings(core, len(match), 16384):
        if s.startswith(match):
            line = s
            break
    if line:
        split_list = line.split("\n")
        if len(split_list) > 1:
            line = split_list[0]
        split_list = line.split("=")
        if len(split_list) > 1:
            vm = split_list[1]
    return vm


def is_core(filename: str) -> bool:
    """
    Parse beginning of the given file to see if it starts with 'KDUMP'
    """
    match = "KDUMP"
    for s in strings(filename, len(match), 64):
        if s.startswith(match):
            return True
    return False


def fixup_args(args: argparse.Namespace) -> None:
    """
    When only one of 'object' or 'core' is supplied, arg 'object'
    could either be a vmlinux or core dump, so we have to sort
    that out.
    """
    if args.object and not args.core and is_core(args.object):
        args.core = args.object
        args.object = ""


def setup_target(args: argparse.Namespace) -> drgn.Program:
    """
    Based on the validated input from the command line, setup the
    drgn.Program for our target and its metadata.
    """
    prog = drgn.Program()
    vml = ""
    fixup_args(args)
    if args.core:
        try:
            prog.set_core_dump(args.core)
        except FileNotFoundError:
            print(f"sdb: no such file: '{args.core}'")
            sys.exit(2)

        # If vmlinux file (args.object) not supplied, try to find its
        # name in the core dump
        if not args.object:
            kernel = detect_from_core(args.core)
            vml = "vmlinux-" + kernel
        else:
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
            if not args.quiet and not args.core:
                print("sdb: " + str(debug_info_err), file=sys.stderr)

    if args.symbol_search:
        try:
            load_debug_info(prog, args.symbol_search, vml)
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


def main() -> None:
    """ The entry point of the sdb "executable" """
    args = parse_arguments()

    try:
        prog = setup_target(args)
    except PermissionError as err:
        print("sdb: " + str(err))
        return

    repl = REPL(prog, list(sdb.get_registered_commands().keys()))
    repl.enable_history(os.getenv('SDB_HISTORY_FILE', '~/.sdb_history'))
    if args.eval:
        exit_code = repl.eval_cmd(args.eval)
        sys.exit(exit_code)
    else:
        repl.start_session()


if __name__ == "__main__":
    main()
