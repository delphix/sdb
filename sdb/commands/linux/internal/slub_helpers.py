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

from typing import Iterable, Optional

import drgn
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.slab import find_containing_slab_cache, for_each_slab_cache

import sdb


def is_root_cache(cache: drgn.Object) -> bool:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    #
    # In v5.9 and later the `memcg_params` field and the concept
    # of root+children caches was completely removed.
    #
    try:
        return int(cache.memcg_params.root_cache.value_()) == 0x0
    except AttributeError:
        return False


def for_each_root_cache() -> Iterable[drgn.Object]:
    #
    # In v5.9 and later the `memcg_params` field and the concept
    # of root+children caches was completely removed.
    #
    try:
        yield from list_for_each_entry(
            "struct kmem_cache",
            sdb.get_object("slab_root_caches").address_of_(),
            "memcg_params.__root_caches_node")
    except KeyError:
        yield from for_each_slab_cache(sdb.get_prog())


def for_each_child_cache(root_cache: drgn.Object) -> Iterable[drgn.Object]:
    assert sdb.type_canonical_name(root_cache.type_) == 'struct kmem_cache *'
    #
    # In v5.9 and later the `memcg_params` field and the concept
    # of root+children caches was completely removed.
    #
    try:
        yield from list_for_each_entry(
            "struct kmem_cache", root_cache.memcg_params.children.address_of_(),
            "memcg_params.children_node")
    except AttributeError:
        yield from []


def for_each_node(cache: drgn.Object) -> Iterable[drgn.Object]:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    node_num = sdb.get_object('nr_node_ids')
    for i in range(node_num):
        yield cache.node[i]


def nr_slabs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    nslabs = 0
    for node in for_each_node(cache):
        nslabs += node.nr_slabs.counter.value_()
    if is_root_cache(cache):
        for child in for_each_child_cache(cache):
            nslabs += nr_slabs(child)
    return nslabs


def entries_per_slab(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return int(cache.oo.x.value_()) & 0xffff


def entry_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return int(cache.size.value_())


def object_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return int(cache.object_size.value_())


def total_memory(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    nslabs = nr_slabs(cache)
    epslab = entries_per_slab(cache)
    esize = entry_size(cache)
    return nslabs * epslab * esize


def objs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    count = 0
    for node in for_each_node(cache):
        count += node.total_objects.counter.value_()
    if is_root_cache(cache):
        for child in for_each_child_cache(cache):
            count += objs(child)
    return count


def inactive_objs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    free = 0
    for node in for_each_node(cache):
        node_partial = node.partial
        for page in list_for_each_entry("struct page",
                                        node_partial.address_of_(), "lru"):
            free += page.objects.value_() - page.inuse.value_()
    if is_root_cache(cache):
        for child in for_each_child_cache(cache):
            free += inactive_objs(child)
    return free


def active_objs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return objs(cache) - inactive_objs(cache)


def active_memory(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return active_objs(cache) * entry_size(cache)


def util(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    total_mem = total_memory(cache)
    if total_mem == 0:
        return 0
    return int((active_memory(cache) / total_mem) * 100)


def lookup_cache_by_address(obj: drgn.Object) -> Optional[drgn.Object]:
    try:
        # The pylint error disabled below is a false positive
        # triggered by some updates to drgn's function signatures.
        # pylint: disable=no-value-for-parameter
        cache = find_containing_slab_cache(obj)
        if cache.value_() == 0x0:
            return None
        return cache
    except drgn.FaultError:
        return None
    return cache
