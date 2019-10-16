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

from sdb.commands.linux.internal import slub_helpers as slub


def list_for_each_spl_kmem_cache(prog: drgn.Program) -> Iterable[drgn.Object]:
    yield from list_for_each_entry("spl_kmem_cache_t",
                                   prog["spl_kmem_cache_list"].address_of_(),
                                   "skc_list")


def backed_by_linux_cache(obj: drgn.Object) -> bool:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_linux_cache.value_() != 0x0


def slab_name(obj: drgn.Object) -> str:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_name.string_().decode('utf-8')


def nr_slabs(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_slab_total.value_()


def slab_alloc(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_slab_alloc.value_()


def slab_size(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_slab_size.value_()


def slab_linux_cache_source(obj: drgn.Object) -> str:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    if not backed_by_linux_cache(obj):
        name = slab_name(obj)
        subsystem = "SPL"
    else:
        name = obj.skc_linux_cache.name.string_().decode('utf-8')
        subsystem = "SLUB"
    return f"{name}[{subsystem:4}]"


def slab_flags(obj: drgn.Object) -> str:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    flag = obj.skc_flags.value_()
    flags_detected = []
    for enum_entry, enum_entry_bit in obj.prog_.type(
            'enum kmc_bit').enumerators:
        if flag & (1 << enum_entry_bit):
            flags_detected.append(enum_entry.replace('_BIT', ''))
    return '|'.join(flags_detected)


def object_size(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_obj_size.value_()


def nr_objects(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    if backed_by_linux_cache(obj):
        return obj.skc_obj_alloc.value_()
    return obj.skc_obj_total.value_()


def obj_alloc(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_obj_alloc.value_()


def obj_inactive(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return nr_objects(obj) - obj_alloc(obj)


def objs_per_slab(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj.skc_slab_objs.value_()


def entry_size(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    if backed_by_linux_cache(obj):
        return slub.entry_size(obj.skc_linux_cache)
    ops = objs_per_slab(obj)
    if ops == 0:
        return 0
    return int(slab_size(obj) / objs_per_slab(obj))


def active_memory(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    return obj_alloc(obj) * entry_size(obj)


def total_memory(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    if backed_by_linux_cache(obj):
        return slub.total_memory(obj.skc_linux_cache)
    return slab_size(obj) * nr_slabs(obj)


def util(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'spl_kmem_cache_t *'
    total_mem = total_memory(obj)
    if total_mem == 0:
        return 0
    return int((active_memory(obj) / total_mem) * 100)
