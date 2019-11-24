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
"""This module contains the "sdb.Locator" class."""

import inspect
from typing import Callable, Iterable, TypeVar

import drgn
import sdb


class Locator(sdb.Command):
    """
    A Locator is a command that locates objects of a given type.
    Subclasses declare that they produce a given output type (the type
    being located), and they provide a method for each input type that
    they can search for objects of this type. Additionally, many
    locators are also PrettyPrinters, and can pretty print the things
    they find. There is some logic here to support that workflow.
    """

    output_type: str = ""

    def no_input(self) -> Iterable[drgn.Object]:
        # pylint: disable=missing-docstring
        raise sdb.CommandError(self.name, 'command requires an input')

    def caller(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        """
        This method will dispatch to the appropriate instance function
        based on the type of the input we receive.
        """

        out_type = self.prog.type(self.output_type)
        has_input = False
        for i in objs:
            has_input = True

            # try subclass-specified input types first, so that they can
            # override any other behavior
            try:
                for (_, method) in inspect.getmembers(self, inspect.ismethod):
                    if not hasattr(method, "input_typename_handled"):
                        continue

                    # Cache parsed type by setting an attribute on the
                    # function that this method is bound to (same place
                    # the input_typename_handled attribute is set).
                    if not hasattr(method, "input_type_handled"):
                        method.__func__.input_type_handled = self.prog.type(
                            method.input_typename_handled)

                    if i.type_ == method.input_type_handled:
                        yield from method(i)
                        raise StopIteration
            except StopIteration:
                continue

            # try passthrough of output type
            # note, this may also be handled by subclass-specified input types
            if i.type_ == out_type:
                yield i
                continue

            # try walkers
            try:
                # pylint: disable=import-outside-toplevel
                #
                # The reason we do the above is that putting
                # the import at the top-level hits a cyclic
                # import error which pretty-much breaks
                # everything. We should reconsider how we
                # handle all our imports.
                from sdb.commands.walk import Walk
                for obj in Walk(self.prog).call([i]):
                    yield drgn.cast(out_type, obj)
                continue
            except sdb.CommandError:
                pass

            # error
            raise sdb.CommandError(
                self.name, 'no handler for input of type {}'.format(i.type_))
        if not has_input:
            yield from self.no_input()

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        # pylint: disable=missing-docstring
        # If this is a hybrid locator/pretty printer, this is where that is
        # leveraged.
        if self.islast and isinstance(self, sdb.PrettyPrinter):
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
