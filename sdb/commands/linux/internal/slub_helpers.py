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


def is_root_cache(cache: drgn.Object) -> bool:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    return cache.memcg_params.root_cache.value_() == 0x0


def for_each_root_cache(prog: drgn.Program) -> Iterable[drgn.Object]:
    yield from list_for_each_entry("struct kmem_cache",
                                   prog["slab_root_caches"].address_of_(),
                                   "memcg_params.__root_caches_node")


def for_each_child_cache(root_cache: drgn.Object) -> Iterable[drgn.Object]:
    assert root_cache.type_.type_name() == 'struct kmem_cache *'
    yield from list_for_each_entry(
        "struct kmem_cache", root_cache.memcg_params.children.address_of_(),
        "memcg_params.children_node")


def nr_slabs(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    nslabs = cache.node[0].nr_slabs.counter.value_()
    if not is_root_cache(cache):
        return nslabs
    for child in list_for_each_entry("struct kmem_cache",
                                     cache.memcg_params.children.address_of_(),
                                     "memcg_params.children_node"):
        nslabs += nr_slabs(child)
    return nslabs


def entries_per_slab(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    return cache.oo.x.value_() & 0xffff


def entry_size(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    return cache.size.value_()


def object_size(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    return cache.object_size.value_()


def total_memory(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    nslabs = nr_slabs(cache)
    epslab = entries_per_slab(cache)
    esize = entry_size(cache)
    return nslabs * epslab * esize


def objs(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    count = cache.node[0].total_objects.counter.value_()
    if not is_root_cache(cache):
        return count
    for child in list_for_each_entry("struct kmem_cache",
                                     cache.memcg_params.children.address_of_(),
                                     "memcg_params.children_node"):
        count += objs(child)
    return count


def inactive_objs(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    node = cache.node[0].partial
    free = 0
    for page in list_for_each_entry("struct page", node.address_of_(), "lru"):
        free += page.objects.value_() - page.inuse.value_()

    if not is_root_cache(cache):
        return free

    for child in list_for_each_entry("struct kmem_cache",
                                     cache.memcg_params.children.address_of_(),
                                     "memcg_params.children_node"):
        free += inactive_objs(child)
    return free


def active_objs(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    return objs(cache) - inactive_objs(cache)


def active_memory(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    return active_objs(cache) * entry_size(cache)


def util(cache: drgn.Object) -> int:
    assert cache.type_.type_name() == 'struct kmem_cache *'
    total_mem = total_memory(cache)
    if total_mem == 0:
        return 0
    return int((active_memory(cache) / total_mem) * 100)
