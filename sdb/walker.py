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
"""This module contains the "sdb.Walker" class."""

from typing import Dict, Iterable, Type

import drgn
import sdb


class Walker(sdb.Command):
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
    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        """
        This function will call walk() on each input object, verifying
        the types as we go.
        """
        assert self.input_type is not None
        type_ = self.prog.type(self.input_type)
        for obj in objs:
            if obj.type_ != type_:
                raise TypeError(
                    'command "{}" does not handle input of type {}'.format(
                        self.names, obj.type_))

            yield from self.walk(obj)
