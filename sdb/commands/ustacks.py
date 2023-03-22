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

        The command will not produce output on running userland processes,
        because the process is not stopped while being analyzed.

    EXAMPLES
        Print the call stacks for all threads

            sdb> stacks
            TID         COUNT
            ==========================================================
            ...
            125023          1
                              0x7f2fd24c1170+0x0
                              spa_open_common+0x1ac
                              dsl_sync_task_common+0x65
                              dsl_sync_task_sig+0x13
                              zcp_eval+0x70f
                              dsl_destroy_snapshots_nvl+0x12b
                              dsl_destroy_snapshot+0x3f
                              ztest_objset_destroy_cb+0xb7
                              dmu_objset_find_impl+0x481
                              dmu_objset_find+0x56
                              ztest_dmu_objset_create_destroy+0xad
                              ztest_execute+0x6c
                              ztest_thread+0xd9
                              zk_thread_wrapper+0x1c
                              0x7f2fd24b6609+0x0
            ...
            125037          1
                              0x7f2fd22ff00b+0x0
                              0x557766d8aeed+0x0
                              ztest_dsl_dataset_promote_busy+0x9e
                              ztest_execute+0x6c
                              ztest_thread+0xd9
                              zk_thread_wrapper+0x1c
                              0x7f2fd24b6609+0x0
            ...

        Print stacks containing the l2arc_feed_thread function

            sdb> stacks -c zcp_eval
            TID         COUNT
            ==========================================================
            125023          1
                              0x7f2fd24c1170+0x0
                              spa_open_common+0x1ac
                              dsl_sync_task_common+0x65
                              dsl_sync_task_sig+0x13
                              zcp_eval+0x70f
                              dsl_destroy_snapshots_nvl+0x12b
                              dsl_destroy_snapshot+0x3f
                              ztest_objset_destroy_cb+0xb7
                              dmu_objset_find_impl+0x481
                              dmu_objset_find+0x56
                              ztest_dmu_objset_create_destroy+0xad
                              ztest_execute+0x6c
                              ztest_thread+0xd9
                              zk_thread_wrapper+0x1c
                              0x7f2fd24b6609+0x0


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
            # This also means that debugging a running userland process will
            # be largely ineffective, since we don't use ptrace to stop the
            # process the way other debuggers like gdb do.
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
        TID         COUNT
        ==========================================================
        125037          1
                          0x7f2fd22ff00b+0x0
                          0x557766d8aeed+0x0
                          ztest_dsl_dataset_promote_busy+0x9e
                          ztest_execute+0x6c
                          ztest_thread+0xd9
                          zk_thread_wrapper+0x1c
                          0x7f2fd24b6609+0x0
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
