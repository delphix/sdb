#
# Copyright 2020, 2025 Delphix
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
import os
from textwrap import shorten
from typing import Callable, Dict, Iterable, List, Optional, Union

import drgn
from drgn.helpers.linux.pid import for_each_task
from drgn.helpers.linux.mm import cmdline

import sdb
from sdb.session import get_trace_manager, is_replay_mode
from sdb.commands.internal.table import Table
from sdb.commands.linux.stacks import KernelStacks
from sdb.error import SymbolNotFoundError

# Maximum width for command line display in threads output
CMDLINE_MAX_WIDTH = 50


def _cmdline(obj: drgn.Object) -> str:
    try:
        ret = cmdline(obj)
        if ret is None:
            return ""
        s = " ".join(map(lambda s: s.decode("utf-8"), ret))

        #
        # The command line for a given thread can be obnoxiously long,
        # so (by default) we limit it to 50 characters here. This helps
        # preserve the readability of the command's output, but comes at
        # the cost of not always showing the full command line of a
        # thread.
        #
        return shorten(s, width=CMDLINE_MAX_WIDTH)
    except drgn.FaultError:
        #
        # The command line information is contained in the user address
        # space of each thread, rather than in the kernel's address
        # space. Thus, often, it may not be possible to retreive the
        # thread's command line; e.g. when reading from a core dump.
        #
        return ""


class KernelThreads(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate and print information about threads (task_stuct)

    COLUMNS
        task - address of the task_struct
        state - the state of the thread
        pid - the pid of the thread's process
        prio - the priority of the thread
        comm - the thread's command
        cmdline - the thread's command line (when available)

    EXAMPLE
        sdb> threads | filter 'obj.comm == "java"' | threads
        task               state         pid  prio comm cmdline
        ------------------ ------------- ---- ---- ---- ----------------------------------------
        0xffff8c96a7c70000 INTERRUPTIBLE 3029 120  java /usr/bin/java -Ddelphix.debug=true [...]
        0xffff8c96a7c71740 INTERRUPTIBLE 3028 120  java /usr/bin/java -Ddelphix.debug=true [...]
        0xffff8c96a7c75d00 INTERRUPTIBLE 3024 120  java /usr/bin/java -Ddelphix.debug=true [...]
        0xffff8c9715808000 INTERRUPTIBLE 3027 120  java /usr/bin/java -Ddelphix.debug=true [...]
    """

    names = ["threads", "thread"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"
    load_on = [sdb.Kernel()]

    FIELDS: Dict[str, Callable[[drgn.Object], Union[str, int]]] = {
        "task": lambda obj: hex(obj.value_()),
        "state": lambda obj: str(KernelStacks.task_struct_get_state(obj)),
        "pid": lambda obj: int(obj.pid),
        "prio": lambda obj: int(obj.prio),
        "comm": lambda obj: str(obj.comm.string_().decode("utf-8")),
        "cmdline": _cmdline,
    }

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        fields = list(KernelThreads.FIELDS.keys())
        table = Table(fields, None, {"task": str})
        for obj in objs:
            row_dict = {
                field: KernelThreads.FIELDS[field](obj) for field in fields
            }
            table.add_row(row_dict["task"], row_dict)
        table.print_()

    def no_input(self) -> Iterable[drgn.Object]:
        # The pylint error disabled below is a false positive
        # triggered by some updates to drgn's function signatures.
        # pylint: disable=no-value-for-parameter
        yield from for_each_task(sdb.get_prog())


def _framestr(frame_index: int, frame: drgn.StackFrame, args: bool) -> str:
    """
    Format a stack frame using drgn StackFrame API properties.

    Args:
        frame_index: Frame index number
        frame: drgn StackFrame object
        args: If True, show function arguments

    Returns:
        Formatted frame string like: "#0  0xaddr in function() at file.c:line:col (inlined)"
    """
    # Format frame index with padding for alignment (e.g., "#0 ", "#10")
    id_str = f"#{frame_index:<2}"

    # Get program counter (address) - pc is always available as a Final[int] attribute
    addr = hex(frame.pc)

    # Get function/symbol name
    function_name = frame.function_name
    if function_name is None:
        try:
            function_name = frame.symbol().name
        except LookupError:
            # No symbol available, just return address
            return f"{id_str} {addr}"

    # Build function string
    if args:
        function_str = " in " + _funcstr(frame)
    else:
        function_str = f" in {function_name}()"

    # Get source location
    try:
        filename, line, column = frame.source()
        # Extract just the filename from the full path
        filename_only = os.path.basename(filename) if filename else "??"
        location_str = f" at {filename_only}:{line}:{column}"
    except LookupError:
        # No source information available
        location_str = ""

    # Add inline marker if applicable
    inline_str = " (inlined)" if frame.is_inline else ""

    return id_str + " " + addr + function_str + location_str + inline_str


def _funcstr(frame: drgn.StackFrame) -> str:
    name = frame.name
    if name is None:
        try:
            name = frame.symbol().name
        except LookupError:
            name = hex(frame.pc)

    func = sdb.get_prog().function(name)
    func_type = func.type_
    func_info = f"{name} ("
    first = True
    for parm in func_type.parameters:
        if not first:
            func_info += ", "
        func_info += f"{parm.name}"
        try:
            val = frame[parm.name].format_(dereference=False,
                                           type_name=False,
                                           member_type_names=False,
                                           member_names=False,
                                           members_same_line=True)
            func_info += f"={val}"
        except KeyError:
            func_info += "=<absent>"
        first = False
    func_info += ")"
    return func_info


class KernelTrace(sdb.Locator, sdb.PrettyPrinter):
    """
    Given a task_struct, trace the thread's execution state.

    FIELDS
        frame# - frame number in backtrace (most recent first)
        addr - address of the frame
        function - function name in the frame (or symbol if no function)
        file - file name (if available) containing the function
        line - line number in the file

    EXAMPLE
        sdb> trace 0xffff94614e796000
        TASK: 0xffff94614e796000 INTERRUPTIBLE PID: 268
        #0  0xffffffffa0c549e8 in context_switch() at core.c:5038:2 (inlined)
        #1  0xffffffffa0c549e8 in __schedule() at core.c:6384:8
        #2  0xffffffffa0c54fe9 in schedule() at core.c:6467:3
        #3  0xffffffffa0c595c2 in schedule_timeout() at timer.c:2116:2
        #4  0xffffffffc04836ae in __cv_timedwait_common() at spl-condvar.c:250:15
        #5  0xffffffffc0483829 in __cv_timedwait_idle() at spl-condvar.c:307:7
        #6  0xffffffffc0571554 in l2arc_feed_thread() at arc.c:9460:10
        #7  0xffffffffc048c8d1 in thread_generic_wrapper() at spl-thread.c:61:3
        #8  0xffffffffa00efb17 in kthread() at kthread.c:334:9
        #9  0xffffffffa0004c3f (ret_from_fork+0x1f/0x2d) at entry_64.S:287
    """

    names = ["trace", "bt"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "task",
            metavar="<task address>",
            nargs="?",
            default=None,
            help="trace this task if no input",
        )
        return parser

    @classmethod
    def help_text(cls) -> List[str]:
        p1 = (
            "If this command is used to end a pipeline, it will print a" +
            " human-readable decoding of the execution state of threads." +
            " Otherwise, it will set the current thread context to the final" +
            " input thread and return the threads that were input to it.")
        p2 = ("This command can be used to start a pipeline, in which" +
              " case it will use the current thread context as input.")
        return [p1, p2]

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        if not self.isfirst and self.args.task:
            raise sdb.CommandError(self.name,
                                   "<task> argument not allowed with input")
        for thread in objs:
            try:
                stack_trace = sdb.get_prog().stack_trace(thread)
            except drgn.FaultError as err:
                raise sdb.CommandError(
                    self.name, f"Thread {hex(thread)} not found") from err
            except LookupError as err:
                raise sdb.CommandError(
                    self.name,
                    f"Thread with id {hex(thread)} not found") from err
            sdb.set_thread(thread)
            print(f"TASK: {hex(thread.value_())} " +
                  str(KernelStacks.task_struct_get_state(thread)) +
                  f" PID: {int(thread.pid)}")
            for frame_index, frame in enumerate(stack_trace):
                if frame.pc == 0:
                    # Note: We filter out frames with zero program counter,
                    # as we often see the stack trace padded with zeros
                    continue
                print(_framestr(frame_index, frame, False))

    def no_input(self) -> Iterable[drgn.Object]:
        if self.args.task:
            try:
                yield sdb.target.create_object("struct task_struct *",
                                               int(self.args.task, 16))
            except ValueError as err:
                raise sdb.CommandError(
                    self.name,
                    f"Invalid task address: '{self.args.task}'") from err
        else:
            yield sdb.get_thread()


class KernelStackFrame(sdb.Locator, sdb.PrettyPrinter):
    """
    Given a task_struct and frame, return requested stack frame

    EXAMPLE
        sdb> frame 7
        #7  0xffffffffc048c8d1 in thread_generic_wrapper (arg=...) at spl-thread.c:61:3
    """

    names = ["stackframe", "frame", "f"]
    input_type = "struct task_struct *"
    output_type = "struct task_struct *"
    load_on = [sdb.Kernel()]
    frame_id = -1

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "frame",
            metavar="<frame>",
            nargs="?",
            default=None,
            type=int,
            help="set local context to this frame number",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="print full file path for frame",
        )
        return parser

    @classmethod
    def help_text(cls) -> List[str]:
        p1 = (
            "This command is used to set the context for the 'locals' and 'registers'"
            +
            " commands. If no frame is specified, the most recent frame is used. If"
            + " no thread is input, the current thread context is used.")
        p2 = ("If this command is used to end a pipeline, it will print a" +
              " human-readable decoding of the requested stack frame for" +
              " each stack trace provided. Otherwise, it will set the current" +
              " frame context to the specified frame and return the threads" +
              " that were input to it.")
        return [p1, p2]

    def _call(
        self,  # pylint: disable=too-many-branches
        objs: Iterable[drgn.Object]
    ) -> Optional[Iterable[drgn.Object]]:
        if self.args.frame >= 0:
            self.frame_id = self.args.frame
            sdb.set_frame(self.frame_id)
        else:
            self.frame_id = sdb.get_frame()
        if self.frame_id == -1:
            raise sdb.CommandError(
                self.name,
                "No frame context set. Use 'frame' command to set frame")
        if self.islast:
            self.pretty_print(objs)
            return None
        # return threads that have the requested frame number
        for thread in objs:
            try:
                if is_replay_mode():
                    frames = _get_replay_frames(thread)
                    if self.frame_id >= len(frames):
                        continue
                else:
                    _frame = sdb.get_prog().stack_trace(thread)[self.frame_id]
            except IndexError:
                continue
            yield thread
        return None

    def pretty_print(
        self,  # pylint: disable=too-many-branches
        objs: Iterable[drgn.Object]) -> None:
        for thread in objs:
            try:
                if is_replay_mode():
                    frames = _get_replay_frames(thread)
                    if self.frame_id >= len(frames):
                        raise IndexError
                    frame = frames[self.frame_id]
                else:
                    frame = sdb.get_prog().stack_trace(thread)[self.frame_id]
                if self.args.verbose:
                    print(frame)
                else:
                    print(_framestr(self.frame_id, frame, True))
            except IndexError:
                print(
                    f"Frame {self.frame_id} out of range for thread {hex(thread)}"
                )
                continue

    def no_input(self) -> Iterable[drgn.Object]:
        yield sdb.get_thread()


class KernelFrameLocals(sdb.Locator, sdb.PrettyPrinter):
    """
    Given a stack frame, return the local variables

    EXAMPLE
        sdb> frame 7 | locals
        arg = (void *)0xffff94614f3cc400
        tp = (thread_priv_t *)0xffff94614f3cc400
        func = (void (*)(void *))l2arc_feed_thread+0x0 = 0xffffffffc05714f0
        args = (void *)0x0
    """

    names = ["locals", "local"]
    input_type = "struct task_struct *"
    output_type = "void *"
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "variables",
            nargs="*",
            default=None,
            metavar="<variable>",
            help="variable to retrieve",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="dereference pointers",
        )
        return parser

    @classmethod
    def help_text(cls) -> List[str]:
        p1 = (
            "This command is used to print the local variables for the frame" +
            " context set by the last 'frame' command." +
            " If no variables are specified, all local variables are printed." +
            " If no thread is input, the current thread context is used.")
        p2 = ("If this command is used to end a pipeline, it will print a" +
              " human-readable decoding of the requested variables for" +
              " each thread provided. Otherwise, it will output the" +
              " requested variable(s) in raw format.")
        return [p1, p2]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        # pylint: disable=too-many-branches
        frame_id = sdb.get_frame()
        if frame_id == -1:
            raise sdb.CommandError(
                self.name,
                "No frame context set. Use 'frame' command to set frame")
        if self.islast:
            self.pretty_print(objs)
            return None
        # return all locals or variables requested
        for thread in objs:
            try:
                if is_replay_mode():
                    frames = _get_replay_frames(thread)
                    if frame_id >= len(frames):
                        continue
                    frame = frames[frame_id]
                else:
                    frame = sdb.get_prog().stack_trace(thread)[frame_id]
                if self.args.variables:
                    for variable in self.args.variables:
                        try:
                            yield frame[variable]
                        except KeyError as err:
                            raise SymbolNotFoundError(self.name,
                                                      variable) from err
                else:
                    for variable in frame.locals():
                        if frame[variable].absent_:
                            continue
                        try:
                            yield frame[variable]
                        except drgn.ObjectAbsentError:
                            continue
            except IndexError:
                continue
        return None

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:  # pylint: disable=too-many-branches
        frame_id = sdb.get_frame()
        for stack in objs:
            if is_replay_mode():
                frames = _get_replay_frames(stack)
                if frame_id >= len(frames):
                    continue
                frame = frames[frame_id]
            else:
                frame = sdb.get_prog().stack_trace(stack)[frame_id]
            if self.args.variables:
                for variable in self.args.variables:
                    try:
                        local = frame[variable]
                        print(
                            f"{variable} = {local.format_(dereference=self.args.verbose)}"
                        )
                    except KeyError:
                        print(
                            f"'{variable}' is not a local variable in this frame"
                        )
                continue
            for variable in frame.locals():
                print(
                    f"{variable} = {frame[variable].format_(dereference=self.args.verbose)}"
                )

    def no_input(self) -> Iterable[drgn.Object]:
        yield sdb.get_thread()


class KernelFrameRegisters(sdb.Locator, sdb.PrettyPrinter):
    """
    Given a stack frame, return the registers

    EXAMPLE
        sdb> frame 7 | registers
        rbx = 18446744072641516784
        rbp = 18446653449961438984
        rsp = 18446653449961438960
        r12 = 18446625744394961920
        r13 = 0
        r14 = 18446653449906223704
        r15 = 18446625744394961920
        rip = 18446744072640579793
    """

    names = ["registers", "register"]
    input_type = "struct task_struct *"
    output_type = "void *"
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "registers",
            nargs="*",
            default=None,
            metavar="<register>",
            help="register to retrieve",
        )
        parser.add_argument(
            "-x",
            "--hex",
            action="store_true",
            help="print registers in hexadecimal",
        )
        return parser

    @classmethod
    def help_text(cls) -> List[str]:
        p1 = (
            "This command is used to print the registers for the frame" +
            " context set by the last 'frame' command." +
            " If no register names are specified, all registers are printed." +
            " If no thread is input, the current thread context is used.")
        p2 = ("If this command is used to end a pipeline, it will print a" +
              " human-readable decoding of the requested registers for" +
              " each thread provided. Otherwise, it will output the" +
              " requested register(s) in raw format.")
        return [p1, p2]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        frame_id = sdb.get_frame()
        if frame_id == -1:
            raise sdb.CommandError(
                self.name,
                "No frame context set. Use 'frame' command to set frame")
        if self.islast:
            self.pretty_print(objs)
            return None
        for stack in objs:
            if is_replay_mode():
                frames = _get_replay_frames(stack)
                if frame_id >= len(frames):
                    continue
                frame = frames[frame_id]
            else:
                frame = sdb.get_prog().stack_trace(stack)[frame_id]
            if self.args.registers:
                for register in self.args.registers:
                    try:
                        yield sdb.target.create_object("void *",
                                                       frame.register(register))
                    except (LookupError, ValueError) as err:
                        raise SymbolNotFoundError(self.name, register) from err
                continue
            registers = frame.registers()
            for value in registers.values():
                yield sdb.target.create_object("void *", value)
        return None

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        # pylint: disable=too-many-branches
        frame_id = sdb.get_frame()
        for stack in objs:
            try:
                if is_replay_mode():
                    frames = _get_replay_frames(stack)
                    if frame_id >= len(frames):
                        raise IndexError
                    frame = frames[frame_id]
                else:
                    frame = sdb.get_prog().stack_trace(stack)[frame_id]
            except IndexError as err:
                raise sdb.CommandError(
                    self.name,
                    f"Frame {frame_id} out of range for thread {hex(stack)}"
                ) from err
            if self.args.registers:
                for register in self.args.registers:
                    try:
                        value = frame.register(register)
                        if self.args.hex:
                            value = hex(value)
                        print(f"{register} = {value}")
                    except LookupError:
                        print(f"{register} = <unavailable>")
                    except ValueError as err:
                        raise SymbolNotFoundError(self.name, register) from err
                continue
            registers = frame.registers()
            if not registers and is_replay_mode():
                print("registers unavailable in replay")
                continue
            for register, value in registers.items():
                if self.args.hex:
                    value = hex(value)
                print(f"{register} = {value}")

    def no_input(self) -> Iterable[drgn.Object]:
        yield sdb.get_thread()


def _get_replay_frames(thread: drgn.Object) -> List[drgn.StackFrame]:
    trace_mgr = get_trace_manager()
    task_addr = int(thread)
    for rec in trace_mgr.threads.values():
        if rec.task_addr == task_addr:
            return list(sdb.get_prog().stack_trace_from_pcs(rec.pcs))
    return []
