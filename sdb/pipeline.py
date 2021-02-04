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
"""This module enables integration with the SDB REPL."""

import subprocess
import sys
import itertools

from typing import Iterable, List, Tuple

import drgn

import sdb.parser as parser
import sdb.target as target
from sdb.error import CommandArgumentsError, CommandNotFoundError
from sdb.command import Address, Cast, Command, get_registered_commands


def massage_input_and_call(
        cmd: Command, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
    """
    Commands can declare that they accept input of type "foo_t*" by
    setting their input_type. They can be passed input of type "void *"
    or "foo_t" and this method will automatically convert the input
    objects to the expected type (foo_t*).
    """

    # If this Command doesn't expect any particular type, just call().
    if cmd.input_type is None:
        yield from cmd.call(objs)
        return

    # If this Command doesn't expect a pointer, just call().
    expected_type = target.get_type(cmd.input_type)
    if expected_type.kind is not drgn.TypeKind.POINTER:
        yield from cmd.call(objs)
        return

    first_obj_type, objs = get_first_type(objs)
    if first_obj_type is not None:

        # If we are passed a void*, cast it to the expected type.
        if (first_obj_type.kind is drgn.TypeKind.POINTER and
                first_obj_type.type.primitive is drgn.PrimitiveType.C_VOID):
            yield from execute_pipeline(objs, [Cast([cmd.input_type]), cmd])
            return

        # If we are passed a foo_t when we expect a foo_t*, use its address.
        if target.type_equals(target.get_pointer_type(first_obj_type),
                              expected_type):
            yield from execute_pipeline(objs, [Address(), cmd])
            return

    yield from cmd.call(objs)


def execute_pipeline(first_input: Iterable[drgn.Object],
                     pipeline: List[Command]) -> Iterable[drgn.Object]:
    """
    This function executes the specified pipeline (i.e. the list of
    Command objects) and yields the output. It recurses through,
    providing each Command of the pipeline the earlier Command's
    output as input.
    """

    if len(pipeline) == 1:
        this_input = first_input
    else:
        this_input = execute_pipeline(first_input, pipeline[:-1])

    yield from massage_input_and_call(pipeline[-1], this_input)


def invoke(myprog: drgn.Program, first_input: Iterable[drgn.Object],
           line: str) -> Iterable[drgn.Object]:
    """
    This function intends to integrate directly with the SDB REPL, such
    that the REPL will pass in the user-specified line, and this
    function is responsible for converting that string into the
    appropriate pipeline of Command objects, and executing it.
    """
    target.set_prog(myprog)

    #
    # Build the pipeline by constructing each of the commands we want to
    # use and building a list of them. If a shell pipeline is constructed
    # at the end save it shell_cmd.
    #
    shell_cmd = None
    pipeline = []
    for cmd, cmd_type in parser.tokenize(line):
        if cmd_type == parser.ExpressionType.CMD:
            name, *args = cmd
            if name not in get_registered_commands():
                raise CommandNotFoundError(name)
            try:
                pipeline.append(get_registered_commands()[name](args, name))
            except SystemExit as cmd_exit:
                #
                # The passed in arguments to each command will be parsed in
                # the command object's constructor. We use "argparse" to do
                # the argument parsing, and when that detects an error, it
                # will throw this exception. Rather than exiting the entire
                # SDB session, we only abort this specific pipeline by raising
                # a CommandArgumentsError.
                #
                raise CommandArgumentsError(name) from cmd_exit
        else:
            assert cmd_type == parser.ExpressionType.SHELL_CMD
            shell_cmd = cmd

    #
    # If we have a !, redirect stdout to a shell process. This avoids
    # having to have a custom printing function that we pass around and
    # use everywhere. We'll fix stdout to point back to the normal stdout
    # at the end.
    #
    if shell_cmd is not None:
        shell_proc = subprocess.Popen(shell_cmd,
                                      shell=True,
                                      stdin=subprocess.PIPE,
                                      encoding="utf-8")
        old_stdout = sys.stdout
        #
        # The type ignore below is due to the following false positive:
        # https://github.com/python/typeshed/issues/1229
        #
        sys.stdout = shell_proc.stdin  # type: ignore[assignment]

    try:
        if pipeline:
            pipeline[0].isfirst = True
            pipeline[-1].islast = True
            yield from execute_pipeline(first_input, pipeline)

        if shell_cmd is not None:
            shell_proc.stdin.flush()
            shell_proc.stdin.close()

    finally:
        if shell_cmd is not None:
            sys.stdout = old_stdout
            shell_proc.wait()


def get_first_type(
        objs: Iterable[drgn.Object]) -> Tuple[drgn.Type, Iterable[drgn.Object]]:
    """
    Determine the type of the first object in the iterable. The first element
    in the iterable will be consumed. Therefore, a tuple is returned with the
    type and a new iterable with the same values as the specified iterable.
    Callers must use the returned iterable in place of the specified one.

    e.g.: first_type, objs = sdb.get_first_type(objs)
    """
    iterator = iter(objs)
    first_obj = next(iterator, None)
    if first_obj is None:
        return None, []
    return first_obj.type_, itertools.chain([first_obj], iterator)
