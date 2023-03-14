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
import textwrap
from typing import Any, Callable, Dict, Iterable, List, Optional, Type, TypeVar

import drgn

from sdb.target import type_canonicalize_name, type_canonical_name, type_canonicalize, get_prog
from sdb.error import CommandError, SymbolNotFoundError
from sdb import target

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
    all_commands[name] = class_


def get_registered_commands() -> Dict[str, Type["Command"]]:
    """
    Return a dictionary of command names to command classes.
    """
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
    def help(cls, name: str) -> None:
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
            print(f"    {line}")

        if len(cls.names) > 1:
            aliases = ", ".join(cls.names)
            print("ALIASES")
            print(f"    {aliases}")
            print()

        indent = "    "
        if issubclass(cls, PrettyPrinter):
            print(
                textwrap.fill(
                    f"If this command is used to end a pipeline, it will print a"
                    f" human-readable decoding of the '{cls.input_type}' objects."
                    f" For the 'raw' object contents, pipe the output of this"
                    f" command into 'echo'.",
                    initial_indent=indent,
                    subsequent_indent=indent))
            print()

        if issubclass(cls, Walker):
            print(
                textwrap.fill(
                    f"This is a Walker for {cls.input_type}. See 'help walk'.",
                    initial_indent=indent,
                    subsequent_indent=indent))
            print()

        if cls.input_type is not None:
            #
            # The pylint error below is a new false-positive because
            # we initialize cls.input type as None by default. A
            # future change could be that everything would work if
            # we initialized it to the empty string instead of None
            # as they have the same semantics as predicates in
            # conditional control flow.
            #
            # pylint: disable=unsubscriptable-object
            it_text = "This command accepts inputs of type 'void *',"
            if cls.input_type[-1] == '*':
                it_text += f" and '{cls.input_type[:-1].strip()}',"
            it_text += f" which will be converted to '{cls.input_type}'."

            print(
                textwrap.fill(it_text,
                              initial_indent=indent,
                              subsequent_indent=indent))
            print()

        if issubclass(cls, Locator):
            # pylint: disable=no-member
            loc_text = (
                f"This is a Locator for {cls.output_type}.  It finds objects"
                f" of this type and outputs or pretty-prints them.  It accepts"
                f" any Walkable type (run 'walk' for a list).")
            if cls.no_input != Locator.no_input:
                loc_text += (
                    f" This command can be used to start a pipeline, in which"
                    f" case it will consume no objects as input; instead it"
                    f" will locate all objects of type '{cls.output_type}',"
                    f" and emit them as output.")
            types = []
            for (_, method) in inspect.getmembers(cls, inspect.isroutine):
                if hasattr(method, "input_typename_handled"):
                    types.append(method.input_typename_handled)
            if len(types) != 0:
                loc_text += (
                    f" Input of the following types is also accepted,"
                    f" in which case the objects of type {cls.output_type}"
                    f" which are associated with them will be located:")
            print(
                textwrap.fill(loc_text,
                              initial_indent=indent,
                              subsequent_indent=indent))
            for type_name in types:
                print(f"{indent}{indent}{type_name}")
            print()

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
                print(f"{line}")
            print()

    #
    # names:
    #    The potential names that can be used to invoke
    #    the command.
    #
    names: List[str] = []

    input_type: Optional[str] = None

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        self.name = name
        self.isfirst = False
        self.islast = False

        self.parser = type(self)._init_parser(name)

        #
        # The if-else clauses below may seem like it can be avoided by:
        #
        #     [1] Passing the `args` function argument to parse_args() even if
        #         it is None - the call won't blow up.
        #
        #  or [2] Setting the default value of `args` to be [] instead of None.
        #
        # Solution [1] doesn't work because parse_args() actually distinguishes
        # between None and [] as parameters. If [] is passed it returns an
        # argparse.Namespace() with default values for all the fields that the
        # command specified in _init_parser(), which is what we want. If None
        # is passed then argparse's default logic is to attempt to parse
        # `_sys.argv[1:]` (reference code: cpython/Lib/argparse.py) which is
        # the arguments passed to the sdb from the shell. This is far from what
        # we want.
        #
        # Solution 2 is dangerous as default arguments in Python are mutable(!)
        # and thus invoking a Command with arguments that doesn't specify the
        # __init__() method can pass its arguments to a similar Command later
        # in the pipeline even if the latter Command didn't specify any args.
        # [docs.python-guide.org/writing/gotchas/#mutable-default-arguments]
        #
        # We still want to set self.args to an argparse.Namespace() with the
        # fields specific to our self.parser, thus we are forced to call
        # parse_args([]) for it, even if `args` is None. This way commands
        # using arguments can always do self.args.<expected field> without
        # having to check whether this field exist every time.
        #
        if args is None:
            args = []
        self.args = self.parser.parse_args(args)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        This method will automatically register the subclass command,
        such that the command will be automatically integrated with the
        SDB REPL.
        """
        #
        # We ignore the type failure below because of the following issue:
        # https://github.com/python/mypy/issues/4660
        #
        super().__init_subclass__(**kwargs)  # type: ignore[call-arg]
        for name in cls.names:
            register_command(name, cls)

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        """
        Implemented by the subclass.
        """
        raise NotImplementedError()

    def __invalid_memory_objects_check(self, objs: Iterable[drgn.Object],
                                       fatal: bool) -> Iterable[drgn.Object]:
        """
        A filter method for objects passed through the pipeline that
        are backed by invalid memory. When `fatal` is set to True
        we raise an error which will stop this control flow when
        such objects are encountered. If `fatal` is False we just
        print the error and go on.
        """
        for obj in objs:
            try:
                obj.read_()
            except TypeError as err:
                obj_type = type_canonicalize(obj.type_)
                if obj_type.kind == drgn.TypeKind.ARRAY and not obj_type.is_complete(
                ) and not obj.absent_:
                    #
                    # This is a zero-length array, let it go through.
                    #
                    yield obj
                    continue
                raise err
            except drgn.FaultError as err:
                if obj.address_ is None:
                    #
                    # This is possible when the object was created `echo`.
                    #
                    err_msg = str(err)
                else:
                    err_msg = f"addresss {hex(obj.address_of_().value_())}"
                err = CommandError(self.name,
                                   f"invalid memory access: {err_msg}")
                if fatal:
                    raise err
                print(err.text)
                continue
            yield obj

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        # pylint: disable=missing-docstring
        #
        # Even though we have __invalid_memory_objects_check() to
        # ensure that the objects returned are valid, we still
        # need to account for invalid accesses happening while
        # the command is running.
        #
        try:
            result = self._call(objs)
            if result is not None:
                #
                # The whole point of the SingleInputCommands are that
                # they don't stop executing in the first encounter of
                # a bad dereference. That's why we check here whether
                # the command that we are running is a subclass of
                # SingleInputCommand and we set the `fatal` flag
                # accordinly.
                #
                yield from self.__invalid_memory_objects_check(
                    result, not issubclass(self.__class__, SingleInputCommand))
        except drgn.FaultError as err:
            raise CommandError(self.name,
                               f"invalid memory access: {str(err)}") from err


class SingleInputCommand(Command):
    """
    Commands that would like to process each input object independently
    (without saving state between objects) can subclass from this class.
    If a FaultError exception is thrown while processing one object,
    processing will continue with the next object.

    Note: A SingleInputCommand cannot also be a Locator, nor a
          PrettyPrinter, nor a Walker currently.
    """

    def _call_one(self, obj: drgn.Object) -> Optional[Iterable[drgn.Object]]:
        """
        Implemented by the subclass.
        """
        raise NotImplementedError()

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            #
            # Even though we have __invalid_memory_objects_check() to
            # ensure that the objects returned are valid, we still
            # need to account for invalid accesses happening while
            # the command is running.
            #
            result = None
            try:
                result = self._call_one(obj)
            except drgn.FaultError as err:
                if obj.address_ is None:
                    #
                    # This is possible when the object was created `echo`.
                    #
                    err_msg = f"invalid memory access: {str(err)}"
                else:
                    err_msg = "invalid memory access while handling object "
                    err_msg += "at address {hex(obj.address_of_().value_())}"
                cmd_err = CommandError(self.name, err_msg)
                print(cmd_err.text)
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

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        if not self.args.type:
            self.parser.error("the following arguments are required: <type>")

        tname = " ".join(self.args.type)
        try:
            self.type = target.get_type(tname)
        except LookupError as err:
            raise CommandError(self.name,
                               f"could not find type '{tname}'") from err

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            try:
                yield drgn.cast(self.type, obj)
            except TypeError as err:
                raise CommandError(self.name, str(err)) from err


class Dereference(Command):
    """
    Dereference the given object (must be pointer).

    EXAMPLES
        Dereference the value of 'jiffies' given the address of it:

            sdb> addr jiffies | deref
            (volatile unsigned long)4905392949

    """

    names = ["deref"]

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            #
            # We canonicalize the type just in case it is a typedef
            # to a pointer (e.g. typedef char* char_p).
            #
            obj_type = type_canonicalize(obj.type_)
            if obj_type.kind != drgn.TypeKind.POINTER:
                raise CommandError(
                    self.name,
                    f"'{obj.type_.type_name()}' is not a valid pointer type")
            if obj_type.type.type_name() == 'void':
                raise CommandError(self.name,
                                   "cannot dereference a void pointer")
            yield drgn.Object(get_prog(),
                              type=obj.type_.type,
                              address=obj.value_())


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
            except KeyError as err:
                raise SymbolNotFoundError(self.name, symbol) from err


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

        For a list of walkers, run 'walk' with no input.

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
            msg += f"no walker found for input of type {input_type}\n"
        msg += "The following types have walkers:\n"
        msg += f"\t{'WALKER':<20s} {'TYPE':<20s}\n"
        for type_, class_ in Walker.allWalkers.items():
            msg += f"\t{class_.names[0]:<20s} {type_:<20s}\n"
        return msg

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        baked = {
            type_canonicalize_name(type_): class_
            for type_, class_ in Walker.allWalkers.items()
        }
        has_input = False
        for i in objs:
            has_input = True

            obj_type = type_canonicalize(i.type_)
            # if type is foo_t change to foo_t *
            if obj_type.kind != drgn.TypeKind.POINTER:
                i = target.create_object(target.get_pointer_type(obj_type),
                                         i.address_)

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
    def __init_subclass__(cls, **kwargs: Any) -> None:
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
        expected_type = type_canonicalize_name(self.input_type)
        for obj in objs:
            canonical_type = type_canonical_name(obj.type_)
            if canonical_type != expected_type:
                raise CommandError(
                    self.name,
                    f'expected input of type {expected_type}, but received {canonical_type}'
                )

            yield from self.walk(obj)


class PrettyPrinter(Command):
    """
    A pretty printer is a command that is designed to format and print
    out a specific type of data, in a human readable way.
    """

    all_printers: Dict[str, Type["PrettyPrinter"]] = {}

    # When a subclass is created, register it
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        assert cls.input_type is not None
        PrettyPrinter.all_printers[cls.input_type] = cls

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        # pylint: disable=missing-docstring
        raise NotImplementedError

    def check_input_type(self,
                         objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        """
        This function acts as a generator, checking that each passed object
        matches the input type for the command
        """
        assert self.input_type is not None
        type_name = type_canonicalize_name(self.input_type)
        for obj in objs:
            if type_canonical_name(obj.type_) != type_name:
                raise CommandError(
                    self.name,
                    f'expected input of type {self.input_type}, but received '
                    f'type {obj.type_}')
            yield obj

    def _call(  # type: ignore[return]
            self,
            objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        """
        This function will call pretty_print() on each input object,
        verifying the types as we go.
        """
        assert self.input_type is not None
        self.pretty_print(self.check_input_type(objs))


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
        baked = {}
        for (_, method) in inspect.getmembers(self, inspect.ismethod):
            if not hasattr(method, "input_typename_handled"):
                continue
            baked[type_canonicalize_name(
                method.input_typename_handled)] = method

        if self.isfirst:
            assert not objs
            yield from self.no_input()
            return

        for i in objs:
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
            raise CommandError(self.name,
                               f'no handler for input of type {i.type_}')

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
