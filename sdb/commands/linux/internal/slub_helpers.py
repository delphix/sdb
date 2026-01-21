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

from typing import Iterable, Optional, Tuple

import drgn
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.slab import (
    find_containing_slab_cache,
    for_each_slab_cache,
    slab_cache_objects_per_slab,
    slab_cache_usage,
)

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


def get_aggregated_usage(cache: drgn.Object) -> Tuple[int, int, int, int]:
    """
    Get slab cache usage statistics, aggregating child caches if applicable.
    Uses drgn's slab_cache_usage() helper internally.

    Returns a tuple of (num_slabs, num_objs, free_objs, active_objs).

    Note: For kernels < v5.9 with memcg enabled, this aggregates statistics
    from child caches as well.
    """
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    usage = slab_cache_usage(cache)
    num_slabs = usage.num_slabs
    num_objs = usage.num_objs
    free_objs = usage.free_objs

    # Aggregate child caches for pre-v5.9 kernels with memcg
    if is_root_cache(cache):
        for child in for_each_child_cache(cache):
            child_usage = slab_cache_usage(child)
            num_slabs += child_usage.num_slabs
            num_objs += child_usage.num_objs
            free_objs += child_usage.free_objs

    num_active_objs = num_objs - free_objs
    return (num_slabs, num_objs, free_objs, num_active_objs)


def nr_slabs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return get_aggregated_usage(cache)[0]


def entries_per_slab(cache: drgn.Object) -> int:
    """
    Get the number of objects in each slab of the given slab cache.
    Uses drgn's slab_cache_objects_per_slab() helper.
    """
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return slab_cache_objects_per_slab(cache)


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
    return get_aggregated_usage(cache)[1]


def inactive_objs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return get_aggregated_usage(cache)[2]


def active_objs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return get_aggregated_usage(cache)[3]


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
