#
# Copyright 2020 Delphix
# Copyright 2021 Datto Inc.
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
from sdb.commands.linux.internal import slub_helpers as slub


class WhatIs(sdb.Command):
    """
    Print the name of the kmem cache from which the address is allocated.

    DESCRIPTION
       The address can be specified as an argument, or
       passed through a pipe.

    EXAMPLES
        Determine the kmem_cache for a given address:

            sdb> whatis 0xfffffe06596e21b8
            0xfffffe06596e21b8 is allocated from dmu_buf_impl_t

        Determine the kmem_cache of address passed through a
        pipe:

            sdb> dbuf |head 1 |deref |member db_buf |whatis
            0xffff8e804368ac80 is allocated from arc_buf_t
    """

    names = ["whatis"]

    @staticmethod
    def print_cache(cache: drgn.Object, addr: str) -> None:
        if cache is None:
            print(f"{addr} does not map to a kmem_cache")
        else:
            assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
            cache_nm = cache.name.string_().decode('utf-8')
            print(f"{addr} is allocated from {cache_nm}")

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("address", nargs="*", metavar="<address>")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        for obj in objs:
            cache = slub.lookup_cache_by_address(obj)
            self.print_cache(cache, hex(int(obj)))
        for addr in self.args.address:
            try:
                obj = sdb.create_object("void *", int(addr, 16))
            except ValueError:
                print(f"{addr} is not a valid address")
                continue
            cache = slub.lookup_cache_by_address(obj)
            self.print_cache(cache, addr)
