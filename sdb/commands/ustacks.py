#
# Copyright 2019, 2023 Delphix
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

# pylint: disable=missing-docstring

import argparse
from typing import Dict, Iterable, List, Optional, Tuple
from collections import defaultdict

import drgn
from drgn import Thread

import sdb


def gettid(thread: Thread) -> drgn.Object:
    return drgn.Object(sdb.get_prog(), 'int', thread.tid)


class UserStacks(sdb.Locator, sdb.PrettyPrinter):
    """
    Print the stack traces for active threads

    DESCRIPTION
        By default, the command will aggregate similar call stacks
        printing them in descending order of frequency. The output
        includes the thread ID and aggregation count.

        Optionally, the command can filter stacks, displaying only
        those that contain a given function.

        The command returns all thread IDs that matched the
        filter.

    EXAMPLES
        Print the call stacks for all threads

            sdb> stacks
            TASK_STRUCT        STATE             COUNT
            ==========================================
            0xffff9521bb3c3b80 IDLE                394
                              __schedule+0x24e
                              schedule+0x2c
                              worker_thread+0xba
                              kthread+0x121
                              ret_from_fork+0x35

            0xffff9521bb3cbb80 INTERRUPTIBLE       384
                              __schedule+0x24e
                              schedule+0x2c
                              smpboot_thread_fn+0x166
                              kthread+0x121
                              ret_from_fork+0x35
            ...

        Print stacks containing the l2arc_feed_thread function

            sdb> stacks -c l2arc_feed_thread
            TASK_STRUCT        STATE             COUNT
            ==========================================
            0xffff9521b3f43b80 INTERRUPTIBLE         1
                              __schedule+0x24e
                              schedule+0x2c
                              schedule_timeout+0x15d
                              __cv_timedwait_common+0xdf
                              __cv_timedwait_sig+0x16
                              l2arc_feed_thread+0x66
                              thread_generic_wrapper+0x74
                              kthread+0x121
                              ret_from_fork+0x35


    """

    names = ["stacks", "stack"]
    input_type = "int"
    output_type = "int"
    load_on = [sdb.Userland()]

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.func_start, self.func_end = 0, 0

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "-a",
            "--all",
            action="store_true",
            help="list all threads for each unique stack trace" +
            " instead of printing a single representative thread")
        parser.add_argument(
            "-c",
            "--function",
            help="only print threads whose stacks contains FUNCTION")
        return parser

    @staticmethod
    def get_frame_pcs(thread: Thread) -> List[int]:
        frame_pcs = []
        try:
            for frame in thread.stack_trace():
                frame_pcs.append(frame.pc)
        except ValueError:
            #
            # Unwinding the stack of a running/runnable task will
            # result in an exception. Since we expect some tasks to
            # be running, we silently ignore this case, and move on.
            #
            # Unfortunately, the exception thrown in this case is a
            # generic "ValueError" exception, so we may wind up
            # masking other "ValueError" exceptions that are not due
            # to unwinding the stack of a running task.
            #
            # We can't check the state of the task here, and verify
            # it's in the "R" state, since that state can change in
            # between the point where the "ValueError" exception was
            # originally raised, and here where we'd verify the
            # state of the task; i.e. it could have concurrently
            # transitioned from running to some other state.
            #
            pass
        return frame_pcs

    def validate_args(self) -> None:
        if self.args.function:
            try:
                #
                # It would be simpler to resolve the symbol from the function
                # name directly but we use the address due to osandov/drgn#47.
                #
                func = sdb.get_object(self.args.function)
                sym = sdb.get_symbol(func.address_of_())
            except KeyError as err:
                raise sdb.CommandError(
                    self.name,
                    f"symbol '{self.args.function}' does not exist") from err
            if func.type_.kind != drgn.TypeKind.FUNCTION:
                raise sdb.CommandError(
                    self.name, f"'{self.args.function}' is not a function")
            self.func_start = sym.address
            self.func_end = self.func_start + sym.size

    def match_stack(self, thread: Thread) -> bool:
        if not self.args.function:
            return True

        for frame_pc in UserStacks.get_frame_pcs(thread):
            if self.func_start <= frame_pc < self.func_end:
                return True
        return False

    def print_header(self) -> None:
        header = f"{'TID':<10}"
        if not self.args.all:
            header += f" {'COUNT':>6s}"
        print(header)
        print("=" * 58)

    #
    # De-duplicate the objs (threads) using a dictionary indexed by
    # task state and program counters. Return a collection sorted by number
    # of tasks per stack.
    #
    @staticmethod
    def aggregate_stacks(
            objs: Iterable[Thread]
    ) -> List[Tuple[Tuple[int, ...], List[Thread]]]:
        stack_aggr: Dict[Tuple[int, ...], List[Thread]] = defaultdict(list)
        for thread in objs:
            stack_key = tuple(UserStacks.get_frame_pcs(thread))
            stack_aggr[stack_key].append(thread)
        return sorted(stack_aggr.items(), key=lambda x: len(x[1]), reverse=True)

    def print_stacks(self, objs: Iterable[Thread]) -> None:
        self.print_header()
        for frame_pcs, threads in UserStacks.aggregate_stacks(objs):
            stacktrace_info = ""

            if self.args.all:
                for thread in threads:
                    stacktrace_info += f"{thread.tid:<10d}\n"
            else:
                tid = threads[0].tid
                stacktrace_info += f"{tid:<10d} {len(threads):6d}\n"

            for frame_pc in frame_pcs:
                try:
                    sym = sdb.get_symbol(frame_pc)
                    func = sym.name
                    offset = frame_pc - sym.address
                except LookupError:
                    func = hex(frame_pc)
                    offset = 0x0
                stacktrace_info += f"{'':18s}{func}+{hex(offset)}\n"
            print(stacktrace_info)

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        self.validate_args()
        self.print_stacks(
            filter(self.match_stack, map(sdb.get_prog().thread, objs)))

    def no_input(self) -> Iterable[drgn.Object]:
        self.validate_args()
        yield from map(gettid, filter(self.match_stack,
                                      sdb.get_prog().threads()))


class UserCrashedThread(sdb.Locator, sdb.PrettyPrinter):
    """
    Print the crashed thread. Only works for crash dumps and core dumps.

    EXAMPLES
        sdb> crashed_thread
        TASK_STRUCT        STATE             COUNT
        ==========================================
        0xffff8f15d7333d00 RUNNING               1
                          __crash_kexec+0x9d
                          __crash_kexec+0x9d
                          panic+0x11d
                          0xffffffff9020b375+0x0
                          __handle_sysrq.cold+0x48
                          write_sysrq_trigger+0x28
                          proc_reg_write+0x43
                          __vfs_write+0x1b
                          vfs_write+0xb9
                          vfs_write+0xb9
                          ksys_write+0x67
                          __x64_sys_write+0x1a
                          __x64_sys_write+0x1a
                          __x64_sys_write+0x1a
                          do_syscall_64+0x57
                          entry_SYSCALL_64+0x94
    """

    names = ["crashed_thread", "panic_stack", "panic_thread"]
    input_type = "int"
    output_type = "int"
    load_on = [sdb.Userland()]

    def validate_args(self) -> None:
        if sdb.get_target_flags() & drgn.ProgramFlags.IS_LIVE:
            raise sdb.CommandError(self.name,
                                   "command only works for core/crash dumps")

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        self.validate_args()
        thread = sdb.get_prog().crashed_thread()
        stacks_obj = UserStacks()
        for obj in objs:
            if obj.value_() != thread.tid:
                raise sdb.CommandError(
                    self.name, "can only pretty print the crashed thread")
            stacks_obj.print_stacks([thread])

    def no_input(self) -> Iterable[drgn.Object]:
        self.validate_args()
        yield from [gettid(sdb.get_prog().crashed_thread())]
