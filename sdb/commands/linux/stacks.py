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

# pylint: disable=missing-docstring

import argparse
from typing import Dict, Iterable, List, Optional, Tuple
from collections import defaultdict

import drgn
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.pid import for_each_task
from drgn.helpers.linux.sched import task_state_to_char

import sdb


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
            " instead of printing a single representative thread")
        parser.add_argument(
            "-c",
            "--function",
            help="only print threads whose stacks contains FUNCTION")
        parser.add_argument(
            "-m",
            "--module",
            help="only print threads whose stacks contain functions from MODULE"
        )
        parser.add_argument(
            "-t",
            "--tstate",
            help="only print threads which are in TSTATE thread state")
        parser.epilog = f'TSTATE := [{", ".join(KernelStacks.TASK_STATES.values()):s}]'
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
        frame_pcs = []
        try:
            for frame in sdb.get_prog().stack_trace(task):
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
        for mod in list_for_each_entry('struct module',
                                       sdb.get_object('modules').address_of_(),
                                       'list'):
            if mod.name.string_().decode("utf-8") == mod_name:
                return (mod.core_layout.base.value_(),
                        mod.core_layout.size.value_())
        return (-1, 0)

    def validate_context(self) -> None:
        #
        # This implementation only works for linux kernel targets
        # (crash dumps or live systems). When support for userland is added we can
        # refactor the kernel code into its own function and switch to the correct
        # codepath depending on the target.
        #
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
                    self.name, f"'{self.args.tstate}' is not a valid task state"
                    f" (acceptable states: {valid_states})")

        if self.args.module:
            if KernelStacks.find_module_memory_segment(
                    self.args.module)[0] == -1:
                raise sdb.CommandError(
                    self.name,
                    f"module '{self.args.module}' doesn't exist or isn't currently loaded"
                )
            self.mod_start, mod_size = KernelStacks.find_module_memory_segment(
                self.args.module)
            assert self.mod_start != -1
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
    def aggregate_stacks(
        objs: Iterable[drgn.Object]
    ) -> List[Tuple[Tuple[str, Tuple[int, ...]], List[drgn.Object]]]:
        stack_aggr: Dict[Tuple[str, Tuple[int, ...]],
                         List[drgn.Object]] = defaultdict(list)
        for task in objs:
            stack_key = (KernelStacks.task_struct_get_state(task),
                         tuple(KernelStacks.get_frame_pcs(task)))
            stack_aggr[stack_key].append(task)
        return sorted(stack_aggr.items(), key=lambda x: len(x[1]), reverse=True)

    def print_stacks(self, objs: Iterable[drgn.Object]) -> None:
        self.print_header()
        for stack_key, tasks in KernelStacks.aggregate_stacks(objs):
            stacktrace_info = ""
            task_state = stack_key[0]

            if self.args.all:
                for task in tasks:
                    stacktrace_info += f"{hex(task.value_()):<18s} {task_state:<16s}\n"
            else:
                task_ptr = hex(tasks[0].value_())
                stacktrace_info += f"{task_ptr:<18s} {task_state:<16s} {len(tasks):6d}\n"

            frame_pcs: Tuple[int, ...] = stack_key[1]
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
        self.validate_context()
        self.print_stacks(filter(self.match_stack, objs))

    def no_input(self) -> Iterable[drgn.Object]:
        self.validate_context()
        yield from filter(self.match_stack, for_each_task(sdb.get_prog()))


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
        thread_obj = sdb.get_prog().crashed_thread().object
        stacks_obj = KernelStacks()
        for obj in objs:
            if obj.value_() != thread_obj.value_():
                raise sdb.CommandError(
                    self.name, "can only pretty print the crashed thread")
            stacks_obj.print_stacks([thread_obj])

    def no_input(self) -> Iterable[drgn.Object]:
        self.validate_context()
        yield from [sdb.get_prog().crashed_thread().object]
