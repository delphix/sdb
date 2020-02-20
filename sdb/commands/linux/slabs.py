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

#
# line-too-long is disabled because of the examples
# added in slub_cache command.
#
# pylint: disable=line-too-long
# pylint: disable=missing-docstring

import argparse
import textwrap
from typing import Any, Dict, Iterable, List, Tuple

import drgn

import sdb
from sdb.commands.internal.fmt import size_nicenum
from sdb.commands.internal.table import Table
from sdb.commands.linux.internal import slub_helpers as slub


class Slabs(sdb.Locator, sdb.PrettyPrinter):

    names = ["slabs"]

    input_type = "struct kmem_cache *"
    output_type = "struct kmem_cache *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            '-H',
            action='store_false',
            help=
            'do not display headers and separate fields by a single tab (scripted mode)'
        )
        parser.add_argument('-o',
                            metavar="FIELDS",
                            help='comma-separated list of fields to display')
        parser.add_argument('-p',
                            action='store_true',
                            help='display numbers in parseable (exact) values')
        parser.add_argument(
            '-r',
            '--recursive',
            action='store_true',
            help='recurse down children caches and print statistics')
        parser.add_argument('-s', metavar="FIELD", help='sort rows by FIELD')
        parser.add_argument('-v',
                            action='store_true',
                            help='Print all statistics')
        #
        # We change the formatter so we can add newlines in the epilog.
        #
        parser.formatter_class = argparse.RawDescriptionHelpFormatter
        parser.epilog = textwrap.fill(
            f"FIELDS := {', '.join(Slabs.FIELDS.keys())}\n",
            width=80,
            replace_whitespace=False)
        parser.epilog += "\n\n"
        parser.epilog += textwrap.fill(
            ("If -o is not specified the default fields used are "
             f"{', '.join(Slabs.DEFAULT_FIELDS)}.\n"),
            width=80,
            replace_whitespace=False)
        parser.epilog += "\n\n"
        parser.epilog += textwrap.fill(
            ("If the -s option is not specified and the command's "
             "output is not piped anywhere then we sort by the "
             "following fields in order: "
             f"{', '.join(Slabs.DEFAULT_SORT_FIELDS)}. "
             "If none of those exists in the field-set we sort by "
             "the first field specified in the set."),
            width=80,
            replace_whitespace=False)
        return parser

    def __no_input_iterator(self) -> Iterable[drgn.Object]:
        for root_cache in slub.for_each_root_cache():
            yield root_cache
            if self.args.recursive:
                yield from slub.for_each_child_cache(root_cache)

    def no_input(self) -> Iterable[drgn.Object]:
        #
        # If this command is not the last term of a pipeline (which
        # means that the pretty-printing code won't run) we still
        # need the `-s` option to work in order to sort the output
        # that will be the input of the next command in the pipeline.
        #
        if self.args.s and not self.islast:
            if self.args.s not in Slabs.FIELDS.keys():
                raise sdb.CommandInvalidInputError(
                    self.name, f"'{self.args.s}' is not a valid field")
            yield from sorted(
                self.__no_input_iterator(),
                key=Slabs.FIELDS[self.args.s],
                reverse=(
                    self.args.s not in Slabs.DEFAULT_INCREASING_ORDER_FIELDS))
        else:
            yield from self.__no_input_iterator()

    FIELDS = {
        "address": lambda obj: hex(obj.value_()),
        "name": lambda obj: obj.name.string_().decode('utf-8'),
        "object_size": slub.object_size,
        "entry_size": slub.entry_size,
        "entries_per_slab": slub.entries_per_slab,
        "slabs": slub.nr_slabs,
        "active_memory": slub.active_memory,
        "total_memory": slub.total_memory,
        "objs": slub.objs,
        "active_objs": slub.active_objs,
        "inactive_objs": slub.inactive_objs,
        "util": slub.util,
    }
    DEFAULT_FIELDS = [
        "name", "entry_size", "active_objs", "active_memory", "total_memory",
        "util"
    ]
    DEFAULT_SORT_FIELDS = ["total_memory", "address", "name"]

    #
    # In general we prefer values to be sorted decreasing order
    # (e.g. show me the slab caches that use up the most memory
    # at the top) but there are certain fields like the ones
    # below where it may make more sense to sort in increasing
    # order like strings where we sort them alphabetically or
    # pointers.
    #
    DEFAULT_INCREASING_ORDER_FIELDS = ["name", "address"]

    def __pp_parse_args(self) -> Tuple[str, List[str], Dict[str, Any]]:
        fields = self.DEFAULT_FIELDS
        if self.args.o:
            #
            # HACK: Until we have a proper lexer for SDB we can
            #       only pass the comma-separated list as a
            #       string (e.g. quoted). Until this is fixed
            #       we make sure to unquote such strings.
            #
            if self.args.o[0] == '"' and self.args.o[-1] == '"':
                self.args.o = self.args.o[1:-1]
            fields = self.args.o.split(",")
        elif self.args.v:
            fields = list(Slabs.FIELDS.keys())

        for field in fields:
            if field not in self.FIELDS:
                raise sdb.CommandError(
                    self.name, "'{:s}' is not a valid field".format(field))

        sort_field = ""
        if self.args.s:
            if self.args.s not in fields:
                msg = f"'{self.args.s}' is not in field set ({', '.join(fields)})"
                raise sdb.CommandInvalidInputError(self.name,
                                                   textwrap.fill(msg, width=80))
            sort_field = self.args.s
        else:
            #
            # If a sort_field hasn't been specified try the following
            # defaults. If these are not part of the field-set then
            # sort by the first field in the set.
            #
            for field in self.DEFAULT_SORT_FIELDS:
                if field in fields:
                    sort_field = field
                    break
            if not sort_field:
                sort_field = fields[0]

        formatters = {
            "total_memory": size_nicenum,
            "active_memory": size_nicenum
        }
        if self.args.p:
            formatters = {}

        return sort_field, fields, formatters

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        sort_field, fields, formatters = self.__pp_parse_args()
        table = Table(fields, set(fields) - {"name"}, formatters)
        for obj in objs:
            row_dict = {field: Slabs.FIELDS[field](obj) for field in fields}
            table.add_row(row_dict[sort_field], row_dict)
        table.print_(print_headers=self.args.H,
                     reverse_sort=(sort_field not in ["name", "address"]))


class SlubCacheWalker(sdb.Walker):
    """
    Walk though all allocated entries in a slub cache.

    EXAMPLES
        Walk through all the objects in the TCP cache:

            sdb> slabs | filter obj.name == "TCP" | walk
            (void *)0xffffa08888af0000
            (void *)0xffffa08888af0880
            (void *)0xffffa08888af1100
            (void *)0xffffa08888af1980
            (void *)0xffffa08888af2200

        Walk though all the ZIOs in the system and print the pool
        that each ZIO belongs to:

            sdb> slabs | filter obj.name == "zio_cache" | slub_cache | cast zio_t * | member io_spa.spa_name
            (char [256])"data"
            (char [256])"rpool"
            (char [256])"rpool"
            (char [256])"rpool"
            (char [256])"rpool"
            (char [256])"rpool"

    NOTES
        This command is not expected to work well for hot caches
        in live systems. The command is implemented using the
        lowest-common denominator functionality provided by the
        default Linux kernel config file that most distros use
        and thus is very inefficient on traversing the entries
        and slabs of each cache.
    """

    names = ["slub_cache"]
    input_type = "struct kmem_cache *"

    def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        yield from slub.for_each_object_in_cache(obj)
