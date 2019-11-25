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

import shlex
import subprocess
import sys
import itertools

from typing import Iterable, List, Optional, Tuple

import drgn  # type: ignore
import sdb


def execute_pipeline(prog: drgn.Program, first_input: Iterable[drgn.Object],
                     pipeline: List["sdb.Command"]) -> Iterable[drgn.Object]:
    """
    This function executes the specified pipeline (i.e. the list of
    sdb.Command objects) and yields the output. It recurses through,
    providing each sdb.Command of the pipeline the earlier sdb.Command's
    output as input.
    """

    if len(pipeline) == 1:
        this_input = first_input
    else:
        this_input = execute_pipeline(prog, first_input, pipeline[:-1])

    result = pipeline[-1].massage_input_and_call(this_input)
    if result is not None:
        yield from result


def execute_pipeline_term(prog: drgn.Program,
                          first_input: Iterable[drgn.Object],
                          pipeline: List["sdb.Command"]) -> None:
    """
    This function is very similar to execute_pipeline, with the
    exception that it doesn't yield any results. This function should be
    used (rather than execute_pipeline) when the last sdb.Command in the
    pipeline doesn't yield any results.
    """

    if len(pipeline) == 1:
        this_input = first_input
    else:
        this_input = execute_pipeline(prog, first_input, pipeline[:-1])

    pipeline[-1].massage_input_and_call(this_input)


def invoke(prog: drgn.Program, first_input: Iterable[drgn.Object],
           line: str) -> Optional[Iterable[drgn.Object]]:
    """
    This function intends to integrate directly with the SDB REPL, such
    that the REPL will pass in the user-specified line, and this
    function is responsible for converting that string into the
    appropriate pipeline of sdb.Command objects, and executing it.
    """

    # pylint: disable=too-many-locals
    # pylint: disable=too-many-branches
    # pylint: disable=too-many-statements

    shell_cmd = None
    # Parse the argument string. Each pipeline stage is delimited by
    # a pipe character "|". If there is a "!" character detected, then
    # pipe all the remaining outout into a subshell.
    lexer = shlex.shlex(line, posix=False, punctuation_chars="|!")
    lexer.wordchars += "();<>&[]"
    all_tokens = list(lexer)
    pipe_stages = []
    tokens: List[str] = []
    for num, token in enumerate(all_tokens):
        if token == "|":
            pipe_stages.append(" ".join(tokens))
            tokens = []
        elif token == "!":
            pipe_stages.append(" ".join(tokens))
            if any(t == "!" for t in all_tokens[num + 1:]):
                print("Multiple ! not supported")
                return
            shell_cmd = " ".join(all_tokens[num + 1:])
            break
        else:
            tokens.append(token)
    else:
        # We didn't find a !, so all remaining tokens are part of
        # the last pipe
        pipe_stages.append(" ".join(tokens))

    # Build the pipeline by constructing each of the commands we want to
    # use and building a list of them.
    pipeline = []
    for stage in pipe_stages:
        (name, _, args) = stage.strip().partition(" ")
        if name not in sdb.all_commands:
            raise sdb.CommandNotFoundError(name)
        try:
            pipeline.append(sdb.all_commands[name](prog, args, name))
        except SystemExit:
            # The passed in arguments to each command will be parsed in
            # the command object's constructor. We use "argparse" to do
            # the argument parsing, and when that detects an error, it
            # will throw this exception. Rather than exiting the entire
            # SDB session, we only abort this specific pipeline by raising
            # a CommandArgumentsError.
            raise sdb.CommandArgumentsError(name)

    pipeline[-1].islast = True

    # If we have a !, redirect stdout to a shell process. This avoids
    # having to have a custom printing function that we pass around and
    # use everywhere. We'll fix stdout to point back to the normal stdout
    # at the end.
    if shell_cmd is not None:
        shell_proc = subprocess.Popen(shell_cmd,
                                      shell=True,
                                      stdin=subprocess.PIPE,
                                      encoding="utf-8")
        old_stdout = sys.stdout
        sys.stdout = shell_proc.stdin  # type: ignore

    try:
        if pipeline[-1].ispipeable:
            yield from execute_pipeline(prog, first_input, pipeline)
        else:
            execute_pipeline_term(prog, first_input, pipeline)

        if shell_cmd is not None:
            shell_proc.stdin.flush()
            shell_proc.stdin.close()

    except BrokenPipeError:
        pass
    finally:
        if shell_cmd is not None:
            sys.stdout = old_stdout
            shell_proc.wait()


def get_first_type(objs: Iterable[drgn.Object]
                  ) -> Tuple[drgn.Type, Iterable[drgn.Object]]:
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
