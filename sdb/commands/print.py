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

import argparse

import drgn
import sdb


class Print(sdb.SingleInputCommand):
    """
    Format output for shell script consumption.

    EXAMPLES
        By default getting the address of a global variable
        looks like this:

            sdb> addr spa_namespace_avl
            (avl_tree_t *)spa_namespace_avl+0x0 = 0xffffffffc0954fe0

        One could use the `print` command to format the above to
        something that is better for programmatic consumption like
        this:

            sdb> addr spa_namespace_avl | print -nr
            0xffffffffc0954fe0
    """

    names = ["print"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        #
        # Check the following for available options that are built-in to drgn:
        # drgn.readthedocs.io/en/latest/api_reference.html#drgn.Object.format_
        #
        parser = super()._init_parser(name)
        parser.add_argument("-c",
                            "--char",
                            action="store_true",
                            help="print character types as character literals")
        parser.add_argument("-d",
                            "--dereference",
                            action="store_true",
                            help="print type name only")
        parser.add_argument("-n",
                            "--nosymbolize",
                            action="store_true",
                            help="skip symbolizing")
        parser.add_argument("-s",
                            "--sameline",
                            action="store_true",
                            help="put all output in a single line")
        parser.add_argument("-r",
                            "--raw",
                            action="store_true",
                            help="don't print type names")
        parser.add_argument(
            "-R",
            "--RAW",
            action="store_true",
            help=("don't symbolize and don't print type names,"
                  " member names in structs, nor indices in arrays"))
        return parser

    def _call_one(self, obj: drgn.Object) -> None:
        raw = self.args.raw
        nosym = self.args.nosymbolize
        if self.args.RAW:
            raw = True
            nosym = True

        print(
            obj.format_(dereference=self.args.dereference,
                        char=self.args.char,
                        symbolize=not nosym,
                        members_same_line=self.args.sameline,
                        type_name=not raw,
                        member_type_names=not raw,
                        element_type_names=not raw,
                        member_names=not self.args.RAW,
                        element_indices=not self.args.RAW))
