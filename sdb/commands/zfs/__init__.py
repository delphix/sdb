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

import glob
import importlib
import os

for path in glob.glob("{}/*.py".format(os.path.dirname(__file__))):
    if path != __file__:
        module = os.path.splitext(os.path.basename(path))[0]
        importlib.import_module("sdb.commands.zfs.{}".format(module))
