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
from typing import Iterable, Tuple
from collections import defaultdict

import drgn
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.pid import for_each_task

import sdb


#
# Note: This is a rudimentary version of what the command could/should be.
#
# On the high-level, it could be a `Locator`, or something similar, where
# objects could be passed as input from the pipeline dispatching different
# methods depending on the type of object. E.g. input could be a namespace
# object and we print all the task structs within it, or it could be just
# a list of task structs passed from a previous command for filtering.
# Another option would be to decouple the stack listing, filtering, and
# pretty-printing functionality to independent SDB commands.
#
# There are also other lower-level usability improvements like supporting
# filtering by `function+offset` with the `-c` option, or by namespace ID
# using `-n <ID>`.
#
# Finally, the command lacks any support for userland targets.
#
# SDB is still in its early stages and hasn't been used enough for us to
# be clear which use cases really matter. In the meantime if we don't have
# anything that provides this functionality it won't be easy to do this
# exploration. The version below is a good enough for the time being
# providing some basic functionality and being our tracer bullet for
# future iterations.
#
class Stacks(sdb.Command):

    names = ["stacks"]

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
        parser.epilog = "TSTATE := [{:s}]".format(", ".join(
            Stacks.TASK_STATES.values()))
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
    }

    @staticmethod
    def task_struct_get_state(task: drgn.Object) -> str:
        state = task.state.value_()
        if state == 0x402:
            return "IDLE"

        exit_state = task.exit_state.value_()
        return Stacks.TASK_STATES[(state | exit_state) & 0x7f]

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

    def validate_args(self, args: argparse.Namespace) -> None:
        if args.function:
            try:
                func = sdb.get_object(args.function)
            except KeyError:
                raise sdb.CommandError(
                    self.name,
                    "symbol '{:s}' does not exist".format(args.function))
            if func.type_.kind != drgn.TypeKind.FUNCTION:
                raise sdb.CommandError(
                    self.name, "'{:s}' is not a function".format(args.function))

        task_states = Stacks.TASK_STATES.values()
        task_states_lowercase = list(map(lambda x: x.lower(), task_states))
        state_shortcuts = Stacks.TASK_STATE_SHORTCUTS
        if args.tstate and not args.tstate.lower(
        ) in task_states_lowercase and not args.tstate in state_shortcuts:
            raise sdb.CommandError(
                self.name,
                "'{:s}' is not a valid task state (acceptable states: {:s})".
                format(args.tstate, ", ".join(task_states)))

        if args.module and Stacks.find_module_memory_segment(
                args.module)[0] == -1:
            raise sdb.CommandError(
                self.name,
                "module '{:s}' doesn't exist or isn't currently loaded".format(
                    args.module))

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-branches

        #
        # As the exception explains the code that follows this statement
        # only works for linux kernel targets (crash dumps or live systems).
        # When support for userland is added we can factor the kernel code
        # that follows into its own function and switch to the correct
        # codepath depending on the target.
        #
        if not sdb.get_target_flags() & drgn.ProgramFlags.IS_LINUX_KERNEL:
            raise sdb.CommandError(self.name,
                                   "userland targets are not supported yet")
        self.validate_args(self.args)

        #
        # Resolve TSTATE shortcut and/or sanitize it to standard uppercase
        # notation if it exists.
        #
        if self.args.tstate:
            if self.args.tstate in Stacks.TASK_STATE_SHORTCUTS:
                self.args.tstate = Stacks.TASK_STATES[
                    Stacks.TASK_STATE_SHORTCUTS[self.args.tstate]]
            else:
                self.args.tstate = self.args.tstate.upper()

        mod_start, mod_end = -1, -1
        if self.args.module:
            mod_start, mod_size = Stacks.find_module_memory_segment(
                self.args.module)
            assert mod_start != -1
            mod_end = mod_start + mod_size

        header = "{:<18} {:<16s}".format("TASK_STRUCT", "STATE")
        if not self.args.all:
            header += " {:>6s}".format("COUNT")
        print(header)
        print("=" * 42)

        #
        # We inspect and group the tasks by recording their state and
        # stack frames once in the following loop. We do this because
        # on live systems state can change under us, thus running
        # something like sdb.get_prog().stack_trace(task) twice (once for
        # grouping and once for printing) could yield different stack
        # traces resulting into misleading output.
        #
        stack_aggr = defaultdict(list)
        for task in for_each_task(sdb.get_prog()):
            stack_key = [Stacks.task_struct_get_state(task)]
            try:
                for frame in sdb.get_prog().stack_trace(task):
                    stack_key.append(frame.pc)
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

            stack_aggr[tuple(stack_key)].append(task)

        for stack_key, tasks in sorted(stack_aggr.items(),
                                       key=lambda x: len(x[1]),
                                       reverse=True):
            task_state = stack_key[0]
            if self.args.tstate and self.args.tstate != task_state:
                continue

            stacktrace_info = ""
            if self.args.all:
                for task in tasks:
                    stacktrace_info += "{:<18s} {:<16s}\n".format(
                        hex(task.value_()), task_state)
            else:
                stacktrace_info += "{:<18s} {:<16s} {:6d}\n".format(
                    hex(tasks[0].value_()), task_state, len(tasks))

            mod_match, func_match = False, False
            for frame_pc in stack_key[1:]:
                if mod_start != -1 and mod_start <= frame_pc < mod_end:
                    mod_match = True

                try:
                    sym = sdb.get_symbol(frame_pc)
                    func, offset = sym.name, frame_pc - sym.address
                    if self.args.function and self.args.function == func:
                        func_match = True
                except LookupError:
                    func, offset = hex(frame_pc), 0x0

                #
                # As a potential future item, we may want to print
                # the frame with the module where the pc/function
                # belongs to. For example:
                #     txg_sync_thread+0x15e [zfs]
                #
                stacktrace_info += "{:18s}{}+{}\n".format("", func, hex(offset))

            if mod_start != -1 and not mod_match:
                continue
            if self.args.function and not func_match:
                continue
            print(stacktrace_info)
        return []
