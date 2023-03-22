#
# Copyright 2020 Delphix
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

from typing import Iterable

import drgn

import sdb
from sdb.commands.ustacks import gettid


class UserThreads(sdb.Locator):
    """
    Locate the list of threads in the process
    """

    names = ["threads", "thread"]
    input_type = "int"
    output_type = "int"
    load_on = [sdb.Userland()]

    def no_input(self) -> Iterable[drgn.Object]:
        yield from map(gettid, sdb.get_prog().threads())
