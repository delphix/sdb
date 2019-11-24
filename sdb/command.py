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
"""This module contains the "sdb.Command" class."""

import argparse
import inspect
from typing import Iterable, List, Optional

import drgn
import sdb


class Command:
    """
    This is the superclass of all SDB command classes.

    This class intends to be the superclass of all other SDB command
    classes, and is responsible for implementing all the logic that is
    required to integrate the command with the SDB REPL.
    """

    # pylint: disable=too-few-public-methods

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        #
        # If the class doesn't have a docstring, "inspect.getdoc" will
        # pull from the parent class's docstring, if the parent class
        # does have a docstring. This is not the behavior we want, so we
        # first check "cls.__doc__" before using "inspect.getdoc".
        #
        if cls.__doc__:
            summary = inspect.getdoc(cls).splitlines()[0].strip()
        else:
            summary = None
        return argparse.ArgumentParser(prog=name, description=summary)

    @classmethod
    def help(cls, name: str):
        """
        This method will print a "help message" for the particular
        command class that it's called on. The docstring and parser for
        the class is used to populate the contents of the message.
        """
        parser = cls._init_parser(name)

        print("SUMMARY")
        for i, line in enumerate(parser.format_help().split('\n')):
            #
            # When printing the help message, the first line will have a
            # "usage: " prefix string which looks awkward, so we strip
            # that prefix prior to printing the first line.
            #
            if i == 0:
                line = line.replace('usage: ', '')
            print("    {}".format(line))

        if len(cls.names) > 1:
            print("ALIASES")
            print("    {}".format(", ".join(cls.names)))
            print()

        #
        # If the class doesn't have a docstring, "inspect.getdoc" will
        # pull from the parent class's docstring, if the parent class
        # does have a docstring. This is not the behavior we want, so we
        # first check "cls.__doc__" before using "inspect.getdoc".
        #
        if cls.__doc__:
            #
            # The first line of the docstring is the summary, which is
            # already be included in the parser description. The second
            # line should be empty. Thus, we skip these two lines.
            #
            for line in inspect.getdoc(cls).splitlines()[2:]:
                print("{}".format(line))
            print()

    #
    # names:
    #    The potential names that can be used to invoke
    #    the command.
    #
    names: List[str] = []

    input_type: Optional[str] = None

    def __init__(self, prog: drgn.Program, args: str = "",
                 name: str = "_") -> None:
        self.prog = prog
        self.name = name
        self.islast = False
        self.ispipeable = False

        if inspect.signature(
                self.call).return_annotation == Iterable[drgn.Object]:
            self.ispipeable = True

        self.parser = type(self)._init_parser(name)
        self.args = self.parser.parse_args(args.split())

    def __init_subclass__(cls, **kwargs):
        """
        This method will automatically register the subclass command,
        such that the command will be automatically integrated with the
        SDB REPL.
        """
        super().__init_subclass__(**kwargs)
        for name in cls.names:
            sdb.register_command(name, cls)

    def call(self,
             objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        # pylint: disable=missing-docstring
        raise NotImplementedError

    def massage_input_and_call(self, objs: Iterable[drgn.Object]
                              ) -> Optional[Iterable[drgn.Object]]:
        """
        Commands can declare that they accept input of type "foo_t*" by
        setting their input_type. They can be passed input of type "void *"
        or "foo_t" and this method will automatically convert the input
        objects to the expected type (foo_t*).
        """

        # If this Command doesn't expect any particular type, just call().
        if self.input_type is None:
            yield from self.call(objs)
            return

        # If this Command doesn't expect a pointer, just call().
        expected_type = self.prog.type(self.input_type)
        if expected_type.kind is not drgn.TypeKind.POINTER:
            yield from self.call(objs)
            return

        first_obj_type, objs = sdb.get_first_type(objs)
        if first_obj_type is not None:
            # If we are passed a void*, cast it to the expected type.
            if (first_obj_type.kind is drgn.TypeKind.POINTER and
                    first_obj_type.type.primitive is drgn.PrimitiveType.C_VOID):
                # pylint: disable=import-outside-toplevel
                #
                # The reason we have to import here is that putting the the
                # import at the top-level hits a cyclic import error which
                # breaks everything. We may need to redesign how we do imports.
                from sdb.commands.cast import Cast
                yield from sdb.execute_pipeline(
                    self.prog, objs, [Cast(self.prog, self.input_type), self])
                return

            # If we are passed a foo_t when we expect a foo_t*, use its address.
            if self.prog.pointer_type(first_obj_type) == expected_type:
                # pylint: disable=import-outside-toplevel
                from sdb.commands.address import Address
                yield from sdb.execute_pipeline(self.prog, objs,
                                                [Address(self.prog), self])
                return

        yield from self.call(objs)
