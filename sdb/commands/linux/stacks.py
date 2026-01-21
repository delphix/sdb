#
# Copyright 2025 Delphix
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

import argparse
from typing import Dict, Iterable, List, Optional, Tuple
from collections import defaultdict

import drgn
from drgn.helpers.linux.pid import for_each_task
from drgn.helpers.linux.sched import task_state_to_char

import sdb
from sdb.session import get_trace_manager, is_replay_mode


class KernelStacks(sdb.Locator, sdb.PrettyPrinter):
    """
    Print the stack traces for active threads (task_struct)

    DESCRIPTION
        By default, the command will aggregate similar call stacks
        printing them in descending order of frequency. The output
        includes the `struct task_struct` address, thread state, and
        aggregation count.

        Optionally, the command can filter stacks, displaying only
        those that match a given thread state, containing a given
        function, or belonging to a given kernel module.

        The command returns all task_stuct structs that matched the
        filter.

    EXAMPLES
        Print the call stacks for all tasks

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

        Print stacks containing functions from the zfs module

            sdb> stacks -m zfs
            TASK_STRUCT        STATE             COUNT
            ==========================================
            0xffff952130515940 INTERRUPTIBLE         1
                              __schedule+0x24e
                              schedule+0x2c
                              cv_wait_common+0x11f
                              __cv_wait_sig+0x15
                              zthr_procedure+0x51
                              thread_generic_wrapper+0x74
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

        Print stacks of threads in the RUNNING state

            sdb> stacks -t RUNNING
            TASK_STRUCT        STATE             COUNT
            ==========================================
            0xffff95214ff31dc0 RUNNING               1

        Count the number of stacks in the zfs module

           sdb> stacks -m zfs | count
           (unsigned long long)12

        Print stacks of the threads started by the zthr command

            sdb> threads | filter obj.comm == "zthr_procedure" | stack
            TASK_STRUCT        STATE             COUNT
            ==========================================
            0xffff9c7e6c268000 INTERRUPTIBLE         5
                              __schedule+0x24e
                              schedule+0x2c
                              cv_wait_common+0x118
                              __cv_wait_sig+0x15
                              zthr_procedure+0x45
                              thread_generic_wrapper+0x74
                              kthread+0x121
                              ret_from_fork+0x1f

            0xffff9c7e6c1f8000 INTERRUPTIBLE         1
                              __schedule+0x24e
                              schedule+0x2c
                              schedule_hrtimeout_range_clock+0xb9
                              schedule_hrtimeout_range+0x13
                              __cv_timedwait_hires+0x117
                              cv_timedwait_hires_common+0x4b
                              cv_timedwait_sig_hires+0x14
                              zthr_procedure+0x96
                              thread_generic_wrapper+0x74
                              kthread+0x121
                              ret_from_fork+0x1f

    """

    names = ["stacks", "stack"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"
    load_on = [sdb.Kernel()]

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.mod_start, self.mod_end = 0, 0
        self.func_start, self.func_end = 0, 0
        self.match_state = ""

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "-a",
            "--all",
            action="store_true",
            help="list all threads for each unique stack trace" +
            " instead of printing a single representative thread",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="print the arguments for each function in the stack trace",
        )
        parser.add_argument(
            "-l",
            "--locals",
            action="store_true",
            help="print local variables in for each function in the stack trace",
        )
        parser.add_argument(
            "-c",
            "--function",
            help="only print threads whose stacks contains FUNCTION")
        parser.add_argument(
            "-m",
            "--module",
            help="only print threads whose stacks contain functions from MODULE",
        )
        parser.add_argument(
            "-t",
            "--tstate",
            help="only print threads which are in TSTATE thread state")
        parser.epilog = f"TSTATE := [{', '.join(KernelStacks.TASK_STATES.values()):s}]"
        return parser

    #
    # See include/linux/sched.h
    #
    TASK_STATES = {
        0x00: "RUNNING",
        0x01: "INTERRUPTIBLE",
        0x02: "UNINTERRUPTIBLE",
        0x04: "STOPPED",
        0x08: "TRACED",
        0x10: "DEAD",
        0x20: "ZOMBIE",
        0x40: "PARKED",
        0x402: "IDLE",
    }

    #
    # See man page of ps(1)
    #
    TASK_STATE_SHORTCUTS = {
        "R": 0x00,
        "S": 0x01,
        "D": 0x02,
        "T": 0x04,
        "t": 0x08,
        "X": 0x10,
        "Z": 0x20,
        "P": 0x40,
        "I": 0x402,
    }

    @staticmethod
    def task_struct_get_state(task: drgn.Object) -> str:
        return KernelStacks.resolve_state(task_state_to_char(task))

    @staticmethod
    def resolve_state(tstate: str) -> str:
        tstate = tstate.upper()
        if tstate in KernelStacks.TASK_STATE_SHORTCUTS:
            return KernelStacks.TASK_STATES[
                KernelStacks.TASK_STATE_SHORTCUTS[tstate]]
        return tstate

    @staticmethod
    def get_frame_pcs(task: drgn.Object) -> List[int]:
        """
        Get the program counters for a task's stack trace.

        In replay mode, uses recorded PCs if available.
        """
        # Check for replay mode first
        if is_replay_mode():
            trace_mgr = get_trace_manager()
            tid = int(task.pid)
            if tid in trace_mgr.threads:
                return trace_mgr.threads[tid].pcs

        frame_pcs = []
        try:
            for frame in sdb.get_prog().stack_trace(task):
                frame_pcs.append(frame.pc)
        except LookupError:
            #
            # Unwinding the stack of a running/runnable task can
            # result in an exception since we expect some tasks to
            # be running. We silently ignore this case, and move on.
            #
            pass
        except ValueError:
            #
            # Unfortunately, one exception thrown in this case is a
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

    #
    # Unfortunately the drgn Symbol API does not specify the namelist
    # that a symbol came from. As a result, we created the following
    # function to implement the `-m` functionality. Whenever we filter
    # by module name, we find the segment in memory where this module
    # resides and do the matching based on the address of the function
    # of the current frame.
    #
    @staticmethod
    def find_module_memory_segment(mod_name: str) -> Tuple[int, int]:
        """
        Looks for the segment in memory where `mod_name` is
        loaded.

        Returns:
            (<base_offset>, <size>) if `mod_name` is found.
            (-1, 0) otherwise.
        """
        # Use drgn's Module API to get address ranges.
        # This handles all kernel version differences internally.
        try:
            mod = sdb.get_prog().module(mod_name)
            ranges = mod.address_ranges

            if not ranges:
                return (-1, 0)

            # Find the overall memory range across all segments
            min_base = min(r[0] for r in ranges)
            max_end = max(r[1] for r in ranges)

            return (min_base, max_end - min_base)
        except LookupError:
            # Module not found
            return (-1, 0)

    def validate_context(self) -> None:
        #
        # This implementation only works for linux kernel targets
        # (crash dumps or live systems). When support for userland is added we can
        # refactor the kernel code into its own function and switch to the correct
        # codepath depending on the target.
        #
        # In replay mode, we allow the command even without IS_LINUX_KERNEL flag
        # since the recorded data is from a kernel session.
        #
        if is_replay_mode():
            self.validate_args()
            return
        if not sdb.get_target_flags() & drgn.ProgramFlags.IS_LINUX_KERNEL:
            raise sdb.CommandError(self.name,
                                   "userland targets are not supported yet")
        self.validate_args()

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

        if self.args.tstate:
            self.match_state = KernelStacks.resolve_state(self.args.tstate)
            task_states = KernelStacks.TASK_STATES.values()
            if self.match_state not in task_states:
                valid_states = ", ".join(task_states)
                raise sdb.CommandError(
                    self.name,
                    f"'{self.args.tstate}' is not a valid task state"
                    f" (acceptable states: {valid_states})",
                )

        if self.args.module:
            self.mod_start, mod_size = KernelStacks.find_module_memory_segment(
                self.args.module)
            if self.mod_start == -1:
                raise sdb.CommandError(
                    self.name,
                    f"module '{self.args.module}' doesn't exist or isn't currently loaded",
                )
            self.mod_end = self.mod_start + mod_size

    def match_stack(self, task: drgn.Object) -> bool:
        if self.args.tstate and self.match_state != KernelStacks.task_struct_get_state(
                task):
            return False

        if not (self.args.module or self.args.function):
            return True

        mod_match, func_match = not self.args.module, not self.args.function
        for frame_pc in KernelStacks.get_frame_pcs(task):
            if not mod_match and self.mod_start <= frame_pc < self.mod_end:
                mod_match = True

            if not func_match and self.func_start <= frame_pc < self.func_end:
                func_match = True

            if mod_match and func_match:
                return True
        return False

    def print_header(self) -> None:
        if is_replay_mode():
            # In replay mode, we show TID and COMM instead of task_struct address
            header = f"{'TID':<12} {'COMM':<16s}"
        else:
            header = f"{'TASK_STRUCT':<18} {'STATE':<16s}"
        if not self.args.all:
            header += f" {'COUNT':>6s}"
        print(header)
        print("=" * 42)

    #
    # De-duplicate the objs (task_structs) using a dictionary indexed by
    # task state and program counters. Return a collection sorted by number
    # of tasks per stack.
    #
    @staticmethod
    def frame_string(frame_info: str, count: int) -> str:
        if count > 1:
            return f"{frame_info} ({str(count)})\n"
        return f"{frame_info}\n"

    @staticmethod
    def aggregate_stacks(
        objs: Iterable[drgn.Object],
    ) -> List[Tuple[Tuple[str, Tuple[int, ...]], List[drgn.Object]]]:
        stack_aggr: Dict[Tuple[str, Tuple[int, ...]],
                         List[drgn.Object]] = defaultdict(list)
        for task in objs:
            stack_key = (
                KernelStacks.task_struct_get_state(task),
                tuple(KernelStacks.get_frame_pcs(task)),
            )
            stack_aggr[stack_key].append(task)
        return sorted(stack_aggr.items(), key=lambda x: len(x[1]), reverse=True)

# pylint: disable=too-many-statements

    def _format_stack_from_pcs(self, pcs: List[int]) -> str:
        """
        Format a stack trace from recorded PCs using hybrid approach.

        Tries drgn stack_trace_from_pcs first (for locals support),
        falls back to recorded symbol lookup.
        """
        trace_mgr = get_trace_manager()
        stacktrace_info = ""

        # First try using drgn's stack_trace_from_pcs if available
        # This provides richer info including potential locals support
        try:
            last_frame_name = ""
            last_offset = 0x0
            count = 0
            frame_info = ""

            for frame in sdb.get_prog().stack_trace_from_pcs(pcs):
                name = frame.name
                if frame.is_inline:
                    if count > 0:
                        stacktrace_info += KernelStacks.frame_string(
                            frame_info, count)
                        count = 0
                    stacktrace_info += f"{'':18s}{name} (inlined)\n"
                    continue
                pc = frame.pc
                if pc == 0x0:
                    continue
                try:
                    sym = frame.symbol()
                    if name is None:
                        name = sym.name
                    offset = pc - sym.address
                except LookupError:
                    if name is None:
                        name = hex(pc)
                    offset = 0x0

                if name == last_frame_name and offset == last_offset:
                    count += 1
                    continue
                if count > 0:
                    stacktrace_info += KernelStacks.frame_string(
                        frame_info, count)
                frame_info = f"{'':18s}{name}+{hex(offset)}"
                last_frame_name = name
                last_offset = offset
                count = 1

            if count > 0:
                stacktrace_info += KernelStacks.frame_string(frame_info, count)

            return stacktrace_info
        except (ValueError, LookupError, TypeError):
            pass  # Fall through to symbol lookup

        # Fallback: use recorded symbols
        last_frame_name = ""
        last_offset = 0x0
        count = 0
        frame_info = ""

        for pc in pcs:
            if pc == 0x0:
                continue

            sym_str = trace_mgr.symbolize_pc(pc)
            # Parse the symbol string to get name and offset
            if '+' in sym_str:
                name, offset_str = sym_str.rsplit('+', 1)
                try:
                    offset = int(offset_str, 16)
                except ValueError:
                    offset = 0x0
            else:
                name = sym_str
                offset = 0x0

            if name == last_frame_name and offset == last_offset:
                count += 1
                continue
            if count > 0:
                stacktrace_info += KernelStacks.frame_string(frame_info, count)
            frame_info = f"{'':18s}{name}+{hex(offset)}"
            last_frame_name = name
            last_offset = offset
            count = 1

        if count > 0:
            stacktrace_info += KernelStacks.frame_string(frame_info, count)

        return stacktrace_info


# pylint: disable=too-many-locals, too-many-statements

    def print_stacks(self, objs: Iterable[drgn.Object]) -> None:
        self.print_header()
        replay = is_replay_mode()

        for stack_key, tasks in KernelStacks.aggregate_stacks(objs):
            stacktrace_info = ""
            task_state = stack_key[0]
            task_ptr = tasks[0]
            frame_pcs = stack_key[1]

            stacktrace_info += f"{hex(task_ptr.value_()):<18s} {task_state:<16s}"
            if self.args.all:
                stacktrace_info += "\n"
                for task in tasks[1:]:
                    stacktrace_info += f"{hex(task.value_()):<18s}\n"
            else:
                stacktrace_info += f" {len(tasks):6d}\n"

            # In replay mode with recorded PCs, use hybrid approach
            if replay and frame_pcs:
                stacktrace_info += self._format_stack_from_pcs(list(frame_pcs))
                print(stacktrace_info)
                continue

            #
            # Normal mode: use drgn stack_trace directly
            # Note: Could also use:
            #    frame_pcs: Tuple[int, ...] = stack_key[1]
            #    sdb.get_prog().stack_trace_from_pcs(frame_pcs)
            #
            # Aggregate frames with the same name and offset.
            #
            last_frame_name = ""
            last_offset = 0x0
            count = 0
            frame_info = ""
            for frame in sdb.get_prog().stack_trace(task_ptr):
                name = frame.name
                if frame.is_inline:
                    # Emit any accumulated frames before inline
                    if count > 0:
                        stacktrace_info += KernelStacks.frame_string(
                            frame_info, count)
                        count = 0
                    stacktrace_info += f"{'':18s}{name} (inlined)\n"
                    continue
                pc = frame.pc
                if pc == 0x0:
                    continue
                try:
                    sym = frame.symbol()
                    if name is None:
                        name = sym.name
                    offset = pc - sym.address
                except LookupError:
                    if name is None:
                        name = hex(pc)
                    offset = 0x0
                # Check if this is a repeat of the last frame
                if name == last_frame_name and offset == last_offset:
                    count += 1
                    continue
                # Emit the last frame we have accumulated
                if count > 0:
                    stacktrace_info += KernelStacks.frame_string(
                        frame_info, count)
                frame_info = f"{'':18s}{name}+{hex(offset)}"
                last_frame_name = name
                last_offset = offset
                count = 1
            # emit the final frame if we have one
            if count > 0:
                stacktrace_info += KernelStacks.frame_string(frame_info, count)
            print(stacktrace_info)

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        self.validate_context()
        if is_replay_mode():
            self._print_replay_stacks()
            return
        self.print_stacks(filter(self.match_stack, objs))

    def no_input(self) -> Iterable[drgn.Object]:
        self.validate_context()

        # In replay mode, return recorded task_struct addresses for pipelines.
        if is_replay_mode():
            trace_mgr = get_trace_manager()
            tasks = []
            for _tid, thread in sorted(trace_mgr.threads.items()):
                if thread.task_addr:
                    tasks.append(
                        sdb.target.create_object("struct task_struct *",
                                                 thread.task_addr))
            return tasks

        # The pylint error disabled below is a false positive
        # triggered by some updates to drgn's function signatures.
        # pylint: disable=no-value-for-parameter
        return self._no_input_live()

    def _no_input_live(self) -> Iterable[drgn.Object]:
        """Generator for live kernel mode - iterates tasks."""
        # pylint: disable=no-value-for-parameter
        yield from filter(self.match_stack, for_each_task(sdb.get_prog()))

    def _print_replay_stacks(self) -> None:
        """Print stacks from recorded thread data in replay mode."""
        trace_mgr = get_trace_manager()
        if not trace_mgr.threads:
            print("No recorded thread stacks available.")
            return

        self.print_header()

        # Group threads by stack signature for aggregation
        stack_groups: Dict[Tuple[int, ...],
                           List[Tuple[int, str]]] = defaultdict(list)
        for tid, thread_rec in trace_mgr.threads.items():
            stack_key = tuple(thread_rec.pcs)
            stack_groups[stack_key].append((tid, thread_rec.comm))

        # Sort by count (descending)
        sorted_groups = sorted(stack_groups.items(),
                               key=lambda x: len(x[1]),
                               reverse=True)

        for pcs, threads in sorted_groups:
            if not pcs:
                continue

            # Get first thread info for display
            first_tid, first_comm = threads[0]
            count = len(threads)

            # Format header with thread info
            # Note: In replay mode we don't have task_struct addresses
            stacktrace_info = f"TID {first_tid:<10d} {first_comm:<16s}"
            if self.args.all:
                stacktrace_info += "\n"
                for tid, comm in threads[1:]:
                    stacktrace_info += f"TID {tid:<10d} {comm:<16s}\n"
            else:
                stacktrace_info += f" {count:6d}\n"

            # Format stack frames using hybrid approach
            stacktrace_info += self._format_stack_from_pcs(list(pcs))
            print(stacktrace_info)


class KernelCrashedThread(sdb.Locator, sdb.PrettyPrinter):
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
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"
    load_on = [sdb.Kernel()]

    def validate_context(self) -> None:
        if sdb.get_target_flags() & drgn.ProgramFlags.IS_LIVE:
            raise sdb.CommandError(self.name,
                                   "command only works for core/crash dumps")

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        self.validate_context()
        if not self.isfirst:
            raise sdb.CommandError(self.name,
                                   "can only pretty print the crashed thread")
        thread_obj = sdb.get_prog().crashed_thread().object
        stacks_obj = KernelStacks()
        stacks_obj.print_stacks([thread_obj])

    def no_input(self) -> Iterable[drgn.Object]:
        self.validate_context()
        yield from [sdb.get_prog().crashed_thread().object]
