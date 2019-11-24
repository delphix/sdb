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
"""
This module contains the "sdb.Command" class, its direct subclasses
(e.g. Walker, PrettyPrinter, Locator), a few very primitive commands
(e.g. Walk, Cast, Address) that are used internally by those templates
but are also exposed, and the functions to manipulate the table of
registered commands during a session.
"""

import argparse
import inspect
from typing import Callable, Dict, Iterable, List, Optional, Type, TypeVar

import drgn

from sdb.target import type_canonicalize_name, type_canonical_name
from sdb.error import CommandError, SymbolNotFoundError
import sdb.target as target

#
# The register_command is used by the Command class when its
# subclasses are initialized (the classes, not the objects),
# so we must define it here, before we import those classes below.
#
all_commands: Dict[str, Type["Command"]] = {}


def register_command(name: str, class_: Type["Command"]) -> None:
    """
    Register the specified command name and command class, such that the
    command will be available from the SDB REPL.
    """
    # pylint: disable=global-statement
    global all_commands
    all_commands[name] = class_


def get_registered_commands() -> Dict[str, Type["Command"]]:
    """
    Return a dictionary of command names to command classes.
    """
    # pylint: disable=global-statement
    global all_commands
    return all_commands


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
        # Note: If "cls.__doc__" exists, then "inspect.getdoc" will not
        #       return thus we ignore the type check warning us that we
        #       may be calling splitlines() for None.
        #
        if cls.__doc__:
            summary = inspect.getdoc(  # type: ignore[union-attr]
                cls).splitlines()[0].strip()
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
        # pylint: disable=too-many-branches
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

        if cls.input_type is not None:
            print("INPUT TYPE")
            print(f"    This command primarily accepts "
                  f"inputs of type {cls.input_type}.")
            print()

        if issubclass(cls, sdb.PrettyPrinter):
            print("PRETTY PRINTER")
            print(f"    This is a PrettyPrinter for {cls.input_type}.")
            print(f"    If prints a human-readable decoding of the object.")
            print(f"    For the raw object contents, pipe the "
                  f"output to 'echo'.")
            print()

        if issubclass(cls, sdb.Walker):
            print("PRETTY PRINTER")
            print(f"    This is a Walker for {cls.input_type}.  "
                  "See 'help walk'.")
            print()

        if issubclass(cls, sdb.Locator):
            # pylint: disable=no-member
            print("LOCATOR")
            print(f"    This is a Locator for {cls.output_type}.")
            print(f"    It finds objects of this type and "
                  f"outputs or pretty-prints them.")
            print(f"    It accepts any Walkable type (run 'walk' for a list).")
            if cls.no_input != sdb.Locator.no_input:
                print(f"    All objects of type {cls.output_type} "
                      f"can be found by ")
                print(f"    running '{name}' as the first "
                      f"command in the pipeline.")
            types = list()
            for (_, method) in inspect.getmembers(cls, inspect.isroutine):
                if hasattr(method, "input_typename_handled"):
                    types.append(method.input_typename_handled)
            if len(types) != 0:
                print("    The following types are also accepted:")
                for type_name in types:
                    print(f"        {type_name}")
                print(f"    Objects of type {cls.output_type} "
                      f"which are associated with the ")
                print(f"    input object will be located.")

        #
        # If the class doesn't have a docstring, "inspect.getdoc" will
        # pull from the parent class's docstring, if the parent class
        # does have a docstring. This is not the behavior we want, so we
        # first check "cls.__doc__" before using "inspect.getdoc".
        #
        # Note: If "cls.__doc__" exists, then "inspect.getdoc" will not
        #       return thus we ignore the type check warning us that we
        #       may be calling splitlines() for None.
        #
        if cls.__doc__:
            #
            # The first line of the docstring is the summary, which is
            # already be included in the parser description. The second
            # line should be empty. Thus, we skip these two lines.
            #
            for line in inspect.getdoc(  # type: ignore[union-attr]
                    cls).splitlines()[2:]:
                print("{}".format(line))
            print()

    #
    # names:
    #    The potential names that can be used to invoke
    #    the command.
    #
    names: List[str] = []

    input_type: Optional[str] = None

    def __init__(self, args: str = "", name: str = "_") -> None:
        self.name = name
        self.islast = False

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
            register_command(name, cls)

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        # pylint: disable=missing-docstring
        raise NotImplementedError

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        # pylint: disable=missing-docstring
        result = self._call(objs)
        if result is not None:
            yield from result


class Cast(Command):
    """
    Cast input objects to specified type

    EXAMPLES

        sdb> echo 0xffffdeadbeef | cast uintptr_t
        (uintptr_t)281474417671919
    """

    names = ["cast"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        #
        # We use REMAINDER here to allow the type to be specified
        # without the user having to worry about escaping whitespace.
        # The drawback of this is an error will not be automatically
        # thrown if no type is provided. To workaround this, we check
        # the parsed arguments, and explicitly throw an error if needed.
        #
        parser.add_argument("type", nargs=argparse.REMAINDER)
        return parser

    def __init__(self, args: str = "", name: str = "_") -> None:
        super().__init__(args, name)
        if not self.args.type:
            self.parser.error("the following arguments are required: <type>")

        tname = " ".join(self.args.type)
        try:
            self.type = target.get_type(tname)
        except LookupError:
            raise CommandError(self.name, f"could not find type '{tname}'")

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            try:
                yield drgn.cast(self.type, obj)
            except TypeError as err:
                raise CommandError(self.name, str(err))


class Address(Command):
    """
    Return address of the given object

    DESCRIPTION
        The command accepts input from both the pipe and the SDB CLI.

        For objects passed from the pipe, their address is returned
        only if they are legitimate objects created from the target
        program being examined. If the objects were created on the
        fly with something like echo and thus don't have an actual
        address in the address space of the program being examined,
        this command just passes on their values as pointers.

        The user can specify one or more inputs as arguments to the
        command. That input can be either the name of a symbol in
        the target (e.g. "jiffies" for vmlinux) or an address (at
        which point this command acts like `echo`).

    EXAMPLES
        Return address of the "jiffies" sumbol:

            sdb> addr jiffies
            *(volatile unsigned long *)0xffffffff97205000 = 4901248625

        Return address of "jiffies", "slab_caches", and also echo
        0xffffdeadbeef.

            sdb> addr jiffies slab_caches 0xffffdeadbeef
            *(volatile unsigned long *)0xffffffff97205000 = 4901290268
            *(struct list_head *)0xffffffff973014c0 = {
                    .next = (struct list_head *)0xffff9d0ada3ca968,
                    .prev = (struct list_head *)0xffff9d0af7002068,
            }
            (void *)0xffffdeadbeef

        Return the addresses of all the root slab caches in the system:

            sdb> slabs | address ! head
            *(struct kmem_cache *)0xffff9d09d40e9500 = {
                    .cpu_slab = (struct kmem_cache_cpu *)0x41d000035820,
                    .flags = (slab_flags_t)1073872896,
            ...
    """

    names = ["address", "addr"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("symbols", nargs="*", metavar="<symbol>")
        return parser

    @staticmethod
    def is_hex(arg: str) -> bool:
        # pylint: disable=missing-docstring
        try:
            int(arg, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def resolve_for_address(arg: str) -> drgn.Object:
        # pylint: disable=missing-docstring
        if Address.is_hex(arg):
            return target.create_object("void *", int(arg, 16))
        return target.get_object(arg).address_of_()

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            if obj.address_ is None:
                #
                # This may not be very intuitive. How can we have
                # an object that doesn't have an address? The answer
                # is that this object was created from sdb (most
                # probably through an echo command that is piped
                # to us) and thus doesn't exist in the address space
                # of our target. This is a weird and rare use-case
                # but it keeps things simple for now. If we ever
                # see this causing problems we should definitely
                # rethink this as being the default behavior. An
                # alternative for example could be that we throw
                # an error that the object doesn't exist in the
                # address space of the target.
                #
                yield obj
            else:
                yield obj.address_of_()

        for symbol in self.args.symbols:
            try:
                yield Address.resolve_for_address(symbol)
            except KeyError:
                raise SymbolNotFoundError(self.name, symbol)


class Walk(Command):
    """
    Dispatch the appropriate walker based on the type of input

    DESCRIPTION
        This command can be used to walk data structures when
        a specific walker for them already exists. There are
        two scenarios when this command is preferable to using
        a specific walker:
        [1] When objects of different types are passed at once
            through a pipe, this walker can dispatch the
            appropriate walker for each of them so the user
            won't need to care about the underlying data
            structure implementations.
        [2] Commands that depend on a data structure being
            traversed can use this command, to reduce the
            lines of code changed when the underlying data
            structure chages.

    EXAMPLES

        sdb> addr spa_namespace_avl | walk
        (void *)0xffff9d0adbe2c000
        (void *)0xffff9d0a2dd28000
        (void *)0xffff9d0ae5040000
        (void *)0xffff9d0a2bdb0000
    """

    names = ["walk"]

    @staticmethod
    def _help_message(input_type: drgn.Type = None) -> str:
        msg = ""
        if input_type is not None:
            msg = msg + "no walker found for input of type {}\n".format(
                input_type)
        msg = msg + "The following types have walkers:\n"
        msg = msg + "\t%-20s %-20s\n" % ("WALKER", "TYPE")
        for type_, class_ in Walker.allWalkers.items():
            msg = msg + "\t%-20s %-20s\n" % (class_.names[0], type_)
        return msg

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        baked = {
            type_canonicalize_name(type_): class_
            for type_, class_ in Walker.allWalkers.items()
        }
        has_input = False
        for i in objs:
            has_input = True
            this_type_name = type_canonical_name(i.type_)
            if this_type_name not in baked:
                raise CommandError(self.name, Walk._help_message(i.type_))

            yield from baked[this_type_name]().walk(i)

        # If we got no input and we're the last thing in the pipeline, we're
        # probably the first thing in the pipeline. Print out the available
        # walkers.
        if not has_input and self.islast:
            print(Walk._help_message())


class Walker(Command):
    """
    A walker is a command that is designed to iterate over data
    structures that contain arbitrary data types.
    """

    allWalkers: Dict[str, Type["Walker"]] = {}

    # When a subclass is created, register it
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        assert cls.input_type is not None
        Walker.allWalkers[cls.input_type] = cls

    def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        # pylint: disable=missing-docstring
        raise NotImplementedError

    # Iterate over the inputs and call the walk command on each of them,
    # verifying the types as we go.
    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        """
        This function will call walk() on each input object, verifying
        the types as we go.
        """
        assert self.input_type is not None
        type_ = target.get_type(self.input_type)
        for obj in objs:
            if obj.type_ != type_:
                raise CommandError(
                    self.name,
                    'expected input of type {}, but received {}'.format(
                        type_, obj.type_))

            yield from self.walk(obj)


class PrettyPrinter(Command):
    """
    A pretty printer is a command that is designed to format and print
    out a specific type of data, in a human readable way.
    """

    all_printers: Dict[str, Type["PrettyPrinter"]] = {}

    # When a subclass is created, register it
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        assert cls.input_type is not None
        PrettyPrinter.all_printers[cls.input_type] = cls

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        # pylint: disable=missing-docstring
        raise NotImplementedError

    def _call(  # type: ignore[return]
            self,
            objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        """
        This function will call pretty_print() on each input object,
        verifying the types as we go.
        """

        assert self.input_type is not None
        type_name = type_canonicalize_name(self.input_type)
        for obj in objs:
            if type_canonical_name(obj.type_) != type_name:
                raise CommandError(
                    self.name,
                    f'exepected input of type {self.input_type}, but received '
                    f'type {obj.type_}')

            self.pretty_print([obj])


class Locator(Command):
    """
    A Locator is a command that locates objects of a given type.
    Subclasses declare that they produce a given output type (the type
    being located), and they provide a method for each input type that
    they can search for objects of this type. Additionally, many
    locators are also PrettyPrinters, and can pretty print the things
    they find. There is some logic here to support that workflow.
    """

    output_type: Optional[str] = None

    def no_input(self) -> Iterable[drgn.Object]:
        # pylint: disable=missing-docstring
        raise CommandError(self.name, 'command requires an input')

    def caller(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        """
        This method will dispatch to the appropriate instance function
        based on the type of the input we receive.
        """

        out_type = None
        if self.output_type is not None:
            out_type = target.get_type(self.output_type)
        baked = dict()
        for (_, method) in inspect.getmembers(self, inspect.ismethod):
            if not hasattr(method, "input_typename_handled"):
                continue
            baked[type_canonicalize_name(
                method.input_typename_handled)] = method

        has_input = False
        for i in objs:
            has_input = True
            obj_type_name = type_canonical_name(i.type_)

            # try subclass-specified input types first, so that they can
            # override any other behavior
            if obj_type_name in baked:
                yield from baked[obj_type_name](i)
                continue

            # try passthrough of output type
            # note, this may also be handled by subclass-specified input types
            if obj_type_name == type_canonical_name(out_type):
                yield i
                continue

            # try walkers
            if out_type is not None:
                try:
                    # pylint: disable=protected-access
                    for obj in Walk()._call([i]):
                        yield drgn.cast(out_type, obj)
                    continue
                except CommandError:
                    pass

            # error
            raise CommandError(
                self.name, 'no handler for input of type {}'.format(i.type_))
        if not has_input:
            yield from self.no_input()

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        # pylint: disable=missing-docstring
        # If this is a hybrid locator/pretty printer, this is where that is
        # leveraged.
        if self.islast and isinstance(self, PrettyPrinter):
            # pylint: disable=no-member
            self.pretty_print(self.caller(objs))
        else:
            yield from self.caller(objs)


T = TypeVar("T", bound=Locator)
IH = Callable[[T, drgn.Object], Iterable[drgn.Object]]


def InputHandler(typename: str) -> Callable[[IH[T]], IH[T]]:
    """
    This is a decorator which should be applied to methods of subclasses of
    Locator. The decorator causes this method to be called when the pipeline
    passes an object of the specified type to this Locator.
    """

    def decorator(func: IH[T]) -> IH[T]:
        func.input_typename_handled = typename  # type: ignore
        return func

    return decorator
