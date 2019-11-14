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
import textwrap
from typing import Any, Callable, Dict, Iterable, List

import drgn

import sdb
from sdb.commands.internal.fmt import size_nicenum
from sdb.commands.internal.table import Table
from sdb.commands.spl.internal import kmem_helpers as kmem


class SplKmemCaches(sdb.Locator, sdb.PrettyPrinter):

    names = ["spl_kmem_caches"]

    input_type = "spl_kmem_cache_t *"
    output_type = "spl_kmem_cache_t *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super(SplKmemCaches, cls)._init_parser(name)
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
            f"FIELDS := {', '.join(SplKmemCaches.FIELDS.keys())}\n",
            width=80,
            replace_whitespace=False)
        parser.epilog += "\n\n"
        parser.epilog += textwrap.fill(
            ("If -o is not specified the default fields used are "
             f"{', '.join(SplKmemCaches.DEFAULT_FIELDS)}.\n"),
            width=80,
            replace_whitespace=False)
        parser.epilog += "\n\n"
        parser.epilog += textwrap.fill(
            ("If the -s option is not specified and the command's "
             "output is not piped anywhere then we sort by the "
             "following fields in order: "
             f"{', '.join(SplKmemCaches.DEFAULT_SORT_FIELDS)}. "
             "If none of those exists in the field-set we sort by "
             "the first field specified in the set."),
            width=80,
            replace_whitespace=False)
        return parser

    def no_input(self) -> Iterable[drgn.Object]:
        #
        # If this command is not the last term of a pipeline (which
        # means that the pretty-printing code won't run) we still
        # need the `-s` option to work in order to sort the output
        # that will be the input of the next command in the pipeline.
        #
        if self.args.s and not self.islast:
            if self.args.s not in SplKmemCaches.FIELDS.keys():
                raise sdb.CommandInvalidInputError(
                    self.name, f"'{self.args.s}' is not a valid field")
            yield from sorted(
                kmem.list_for_each_spl_kmem_cache(self.prog),
                key=SplKmemCaches.FIELDS[self.args.s],
                reverse=(self.args.s not in
                         SplKmemCaches.DEFAULT_INCREASING_ORDER_FIELDS))
        else:
            yield from kmem.list_for_each_spl_kmem_cache(self.prog)

    FIELDS = {
        "address": lambda obj: hex(obj.value_()),
        "name": kmem.slab_name,
        "flags": kmem.slab_flags,
        "object_size": kmem.object_size,
        "entry_size": kmem.entry_size,
        "slab_size": kmem.slab_size,
        "objects_per_slab": kmem.objs_per_slab,
        "entries_per_slab": kmem.objs_per_slab,
        "slabs": kmem.nr_slabs,
        "active_slabs": kmem.slab_alloc,
        "active_memory": kmem.active_memory,
        "total_memory": kmem.total_memory,
        "objs": kmem.nr_objects,
        "active_objs": kmem.obj_alloc,
        "inactive_objs": kmem.obj_inactive,
        "source": kmem.slab_linux_cache_source,
        "util": kmem.util,
    }
    DEFAULT_FIELDS = [
        "name",
        "entry_size",
        "active_objs",
        "active_memory",
        "source",
        "total_memory",
        "util",
    ]
    DEFAULT_SORT_FIELDS = ["active_memory", "address", "name"]

    #
    # In general we prefer values to be sorted decreasing order
    # (e.g. show me the slab caches that use up the most memory
    # at the top) but there are certain fields like the ones
    # below where it may make more sense to sort in increasing
    # order like strings where we sort them alphabetically or
    # pointers.
    #
    DEFAULT_INCREASING_ORDER_FIELDS = ["name", "address"]

    def __pp_parse_args(self
                       ) -> (str, List[str], Dict[str, Callable[[Any], str]]):
        fields = SplKmemCaches.DEFAULT_FIELDS
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
            fields = list(SplKmemCaches.FIELDS.keys())

        for field in fields:
            if field not in SplKmemCaches.FIELDS:
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
            "active_memory": size_nicenum,
            "total_memory": size_nicenum
        }
        if self.args.p:
            formatters = {}

        return sort_field, fields, formatters

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        sort_field, fields, formatters = self.__pp_parse_args()
        table = Table(fields, set(fields) - {"name"}, formatters)
        for obj in objs:
            row_dict = {
                field: SplKmemCaches.FIELDS[field](obj) for field in fields
            }
            table.add_row(row_dict[sort_field], row_dict)
        table.print_(print_headers=self.args.H,
                     reverse_sort=(sort_field not in ["name", "address"]))
