#
# Copyright 2019 Chuck Tuffli
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

import sys
from typing import Iterable

import drgn
import sdb


class Echo(sdb.Command):
    # pylint: disable=too-few-public-methods

    names = ["exit", "quit"]

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        sys.exit()
