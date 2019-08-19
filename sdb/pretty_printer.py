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
"""This module contains the "sdb.PrettyPrinter" class."""

from typing import Dict, Iterable, Type

import drgn
import sdb

#
# A Pretty Printer is a command that is designed to format and print out
# a specific type of data, in a human readable way.
#


class PrettyPrinter(sdb.Command):
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

    def call(self, objs: Iterable[drgn.Object]) -> None:
        """
        This function will call pretty_print() on each input object,
        verifying the types as we go.
        """

        assert self.input_type is not None
        type_ = self.prog.type(self.input_type)
        for obj in objs:
            if obj.type_ != type_:
                raise TypeError(
                    'command "{}" does not handle input of type {}'.format(
                        self.names, obj.type_))

            self.pretty_print([obj])
