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

# pylint: disable=missing-docstring

import argparse
from typing import Iterable

import drgn
import sdb


class Member(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["member"]

    def _init_argparse(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("members", nargs="+", metavar="<member>")

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            for member in self.args.members:
                try:
                    obj = obj.member_(member)
                except (LookupError, TypeError) as err:
                    #
                    # The expected error messages that we get from
                    # member_() are good enough to be propagated
                    # as-is.
                    #
                    raise sdb.CommandError(self.name, str(err))
            yield obj
