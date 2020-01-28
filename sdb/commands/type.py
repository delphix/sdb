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

import drgn
import sdb


class Type(sdb.SingleInputCommand):
    """
    Print the type of the objects passed in the pipeline

    EXAMPLES
        Print the object type returned by the spa command

            sdb> spa | type
            spa_t *
    """

    names = ["type"]

    def _call_one(self, obj: drgn.Object) -> None:
        print(obj.type_)
