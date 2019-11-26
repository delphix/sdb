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

from typing import Iterable

import drgn
from drgn.helpers.linux.list import list_for_each_entry

import sdb
from sdb.commands.linux.internal import slub_helpers as slub


def list_for_each_spl_kmem_cache() -> Iterable[drgn.Object]:
    yield from list_for_each_entry(
        "spl_kmem_cache_t",
        sdb.get_object("spl_kmem_cache_list").address_of_(), "skc_list")


def backed_by_linux_cache(cache: drgn.Object) -> bool:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_linux_cache.value_() != 0x0


def slab_name(cache: drgn.Object) -> str:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_name.string_().decode('utf-8')


def nr_slabs(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_slab_total.value_()


def slab_alloc(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_slab_alloc.value_()


def slab_size(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_slab_size.value_()


def slab_linux_cache_source(cache: drgn.Object) -> str:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    if not backed_by_linux_cache(cache):
        name = slab_name(cache)
        subsystem = "SPL"
    else:
        name = cache.skc_linux_cache.name.string_().decode('utf-8')
        subsystem = "SLUB"
    return f"{name}[{subsystem:4}]"


def slab_flags(cache: drgn.Object) -> str:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    flag = cache.skc_flags.value_()
    flags_detected = []
    for enum_entry, enum_entry_bit in cache.prog_.type(
            'enum kmc_bit').enumerators:
        if flag & (1 << enum_entry_bit):
            flags_detected.append(enum_entry.replace('_BIT', ''))
    return '|'.join(flags_detected)


def object_size(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_obj_size.value_()


def nr_objects(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    if backed_by_linux_cache(cache):
        return cache.skc_obj_alloc.value_()
    return cache.skc_obj_total.value_()


def obj_alloc(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_obj_alloc.value_()


def obj_inactive(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return nr_objects(cache) - obj_alloc(cache)


def objs_per_slab(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return cache.skc_slab_objs.value_()


def entry_size(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    if backed_by_linux_cache(cache):
        return slub.entry_size(cache.skc_linux_cache)
    ops = objs_per_slab(cache)
    if ops == 0:
        return 0
    return int(slab_size(cache) / objs_per_slab(cache))


def active_memory(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    return obj_alloc(cache) * entry_size(cache)


def total_memory(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    if backed_by_linux_cache(cache):
        return slub.total_memory(cache.skc_linux_cache)
    return slab_size(cache) * nr_slabs(cache)


def util(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'spl_kmem_cache_t *'
    total_mem = total_memory(cache)
    if total_mem == 0:
        return 0
    return int((active_memory(cache) / total_mem) * 100)
