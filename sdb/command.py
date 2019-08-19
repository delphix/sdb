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

    #
    # names:
    #    The potential names that can be used to invoke
    #    the command.
    #
    names: List[str] = []

    #
    # name:
    #    The name used when the command was invoked. This
    #    is generally used as a parameter passed to
    #    exceptions raised by SDB to make error messages
    #    more precise.
    #
    name: str = ""

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

        parser = argparse.ArgumentParser(prog=name)
        self._init_argparse(parser)
        self.args = parser.parse_args(args.split())

    def __init_subclass__(cls, **kwargs):
        """
        This method will automatically register the subclass command,
        such that the command will be automatically integrated with the
        SDB REPL.
        """
        super().__init_subclass__(**kwargs)
        for name in cls.names:
            sdb.register_command(name, cls)

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        pass

    def call(self,
             objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        # pylint: disable=missing-docstring
        raise NotImplementedError
