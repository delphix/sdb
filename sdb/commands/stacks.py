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
from typing import Iterable

import drgn
import sdb
from drgn.helpers.linux.pid import for_each_task

class FrameInfo():

    def __init__(self, function, offset, module):
        self.function = function
        self.offset = offset
        self.module = module

    def display_str(self):
        mod = ""
        if self.module and not self.module.startswith("vmlinux"): # TODO is this accurate?
            mod = " [" + self.module + "]"
        return self.location_str() + mod

    def location_str(self):
        offset = ""
        if self.offset is not None:
            offset = "+" + hex(self.offset)
        return self.function + offset

# TODO print thread numbers for all matched (-a)

class StackInfo():
    def __init__(self, frames, state, task_struct: int):
        self.frames = frames
        self.state = state
        # An example task with this stack
        self.task_struct = task_struct
        self.count = 1

    def get_key(self):
        return self.state + ''.join(f.location_str() for f in self.frames)

    def pretty_print(self):
        print('{0:x}   {1} {2:>5}'.format(self.task_struct, self.state.ljust(30), self.count))
        indent = '                   '
        print(indent + ("\n" + indent).join(f.display_str() for f in self.frames))
        print("")

class Stacks(sdb.Command):

    names = ["stacks"]

    # This seems a little gross, but a new instance of this class is invoked each time. And
    # there won't be multiple instances of this class at a time, will there be?
    stack_map = {}

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        super().__init__(prog, args, name)

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('-m', help='show stacks with a function in module M')
        parser.add_argument('-c', help='show stacks with function C')
        parser.add_argument('-t', help='show threads with status T') #TODO list optional states
        parser.add_argument('-f', action='store_true', help='force a refresh of the stacks cache')

    def print_stacks(filter_module, filter_function, filter_state):
        matching_count=0

        for key, stack_info in sorted(Stacks.stack_map.items(), key = lambda val: val[1].count, reverse=True):
            frames = stack_info.frames

            state_match = True
            module_match = True
            function_match = True
            if filter_state is not None:
                # TODO maybe make this case insitive?
                # Also, maybe allow single letter state identifiers (D for uninterruptible sleep, R for running, etc)?
                state_match = filter_state == stack_info.state
            if filter_module is not None:
                module_match = any([filter_module == frame.module for frame in frames])
            if filter_function is not None:
                # filter is allowed to match '<function>' or '<function>+<offset>'
                function_match = any([frame.function == filter_function or frame.location_str() == filter_function for frame in frames])

            if state_match and module_match and function_match:
                stack_info.pretty_print()
                matching_count += 1

        # TODO would these be better printed up front?
        print("Total unique stacks:", len(Stacks.stack_map.keys()))
        # TODO maybe only print this vv is a filter was applied?
        print("Matching unique stacks:", matching_count)

    def get_state(task):
        # TODO what to do here for userspace threads?

        # See include/linux/sched.h
        TASK_STATES = {
               0x00 : "RUNNING",
               0x01 : "INTERRUPTIBLE",
               0x02 : "UNINTERRUPTIBLE",
               0x04 : "STOPPED",
               0x08 : "TRACED",
               0x10 : "DEAD",
               0x20 : "ZOMBIE",
               0x40 : "PARKED",
        }

        state = task.state.value_()
        exit_state = task.exit_state.value_()
        if state == 0x402:
            return "IDLE"
        else:
            return TASK_STATES[(state | exit_state) & 0x7f]

    def build_stack_map(self):
        stack_map = {}

        # TODO only iterate over all threads if this is first stage in pipeline. Otherwise,
        # expect to be passed an iterable of task_structs
        # TODO this only iterates over the tasks in the initial namespace. The default should
        # probably be to iterate over all of the tasks in all of the namespaces
        for task in drgn.helpers.linux.pid.for_each_task(self.prog):
            frames=[]
            for frame in self.prog.stack_trace(task):
                try: 
                    sym = frame.symbol()
                except LookupError:
                    sym = None

                if sym:
                    function_name = sym.name
                    module = None # TODO is this available through drgn?
                    offset = frame.pc - sym.address
                else:
                    function_name = hex(frame.pc)
                    module = None
                    offset = None

                frames.append(FrameInfo(function_name, offset, module))

            stack_info = StackInfo(frames, Stacks.get_state(task), task.value_())
            key = stack_info.get_key()
            if (key in stack_map):
                stack_map[key].count += 1
            else:
                stack_map[key] = stack_info

        return stack_map

    def call(self, objs: Iterable[drgn.Object]) -> None:
        args = self.args

        if not any(Stacks.stack_map) or args.f:
            Stacks.stack_map = self.build_stack_map()

        # TODO the help for this command should explain that TASK is the task
        # struct of a random thread which has this stack
        print("TASK               STATE                          COUNT")
        print("=======================================================")
        Stacks.print_stacks(args.m, args.c, args.t)
