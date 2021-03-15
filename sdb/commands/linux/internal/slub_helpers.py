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

from typing import Iterable, Set, Optional

import drgn
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.mm import for_each_page, page_to_virt, virt_to_pfn, pfn_to_page

import sdb


def is_root_cache(cache: drgn.Object) -> bool:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    return int(cache.memcg_params.root_cache.value_()) == 0x0


def for_each_root_cache() -> Iterable[drgn.Object]:
    yield from list_for_each_entry(
        "struct kmem_cache",
        sdb.get_object("slab_root_caches").address_of_(),
        "memcg_params.__root_caches_node")


def for_each_child_cache(root_cache: drgn.Object) -> Iterable[drgn.Object]:
    assert sdb.type_canonical_name(root_cache.type_) == 'struct kmem_cache *'
    yield from list_for_each_entry(
        "struct kmem_cache", root_cache.memcg_params.children.address_of_(),
        "memcg_params.children_node")


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


def cache_red_left_padding(cache: drgn.Object) -> int:
    SLAB_RED_ZONE_FLAG = 0x00000400
    padding = 0
    if cache.flags & SLAB_RED_ZONE_FLAG:
        padding += int(cache.red_left_pad)
    return padding


def lookup_cache_by_address(obj: drgn.Object) -> Optional[drgn.Object]:
    pfn = virt_to_pfn(sdb.get_prog(), obj)
    page = pfn_to_page(pfn)
    cache = page.slab_cache
    try:
        # read the name to force FaultError if any
        _ = cache.name.string_().decode('utf-8')
    except drgn.FaultError:
        return None
    return cache


def cache_get_free_pointer(cache: drgn.Object, p: drgn.Object) -> drgn.Object:
    """
    Get the next pointer in the freelist. Note, that this
    function assumes that CONFIG_SLAB_FREELIST_HARDENED
    is set in the target
    """
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    assert sdb.type_canonical_name(p.type_) == 'void *'
    hardened_ptr = p + cache.offset.value_()

    #
    # We basically do what `freelist_dereference()` and
    # `freelist_ptr()` do in the kernel source:
    #
    # ptr <- (void *)*(unsigned long *)(hardened_ptr)
    #
    intermediate_ulong = drgn.Object(sdb.get_prog(),
                                     type='unsigned long',
                                     address=hardened_ptr.value_())
    ptr = drgn.Object(sdb.get_prog(),
                      type='void *',
                      value=intermediate_ulong.value_())

    #
    # ptr_addr <- (unsigned long)hardened_ptr
    #
    ptr_addr = drgn.Object(sdb.get_prog(),
                           type='unsigned long',
                           value=hardened_ptr.value_())

    #
    # return (void *)((unsigned long)ptr ^ cache->random ^ ptr_addr)
    #
    ptr_as_ulong = drgn.Object(sdb.get_prog(),
                               type='unsigned long',
                               value=ptr.value_())
    clean_ptr_val = ptr_as_ulong.value_()
    clean_ptr_val ^= cache.random.value_()
    clean_ptr_val ^= ptr_addr.value_()
    return drgn.Object(sdb.get_prog(), type='void *', value=clean_ptr_val)


def for_each_freeobj_in_slab(cache: drgn.Object,
                             page: drgn.Object) -> Iterable[drgn.Object]:
    """
    Return all the free objects in this slab.
    """
    p = page.freelist
    while p.value_() != 0x0:
        yield p
        p = cache_get_free_pointer(cache, p)


def for_each_partial_slab_in_cache(cache: drgn.Object) -> Iterable[drgn.Object]:
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    for node in for_each_node(cache):
        node_partial = node.partial
        yield from list_for_each_entry("struct page",
                                       node_partial.address_of_(), "lru")

    if is_root_cache(cache):
        for child in for_each_child_cache(cache):
            yield from for_each_partial_slab_in_cache(child)


def for_each_object_in_cache(cache: drgn.Object) -> Iterable[drgn.Object]:
    """
    Goes through each object in the SLUB cache supplied
    yielding them to the consumer.
    """
    assert sdb.type_canonical_name(cache.type_) == 'struct kmem_cache *'
    pg_slab_flag = 1 << sdb.get_prog().constant('PG_slab').value_()

    cache_children = {child.value_() for child in for_each_child_cache(cache)}
    #
    # We are caching the list of partial slabs here so later we can
    # decide whether we want to use the freelist to find which entries
    # are allocated (partial slab case) or just read all the entries
    # (full slab case). This is not great for live-systems where these
    # data can be changing very quickly under us but its the best that
    # we can do given that the Linux kernel doesn't keep track of its
    # full slabs explicitly except in cases where very heavy-weight
    # debugging config options are enabled.
    #
    cache_partials = {
        partial_slab.value_()
        for partial_slab in for_each_partial_slab_in_cache(cache)
    }

    #
    # For the same reason mentioned above, since the Linux kernel
    # doesn't keep track of its full slabs by default in a list
    # as it does for partial slabs, we have to go through all the
    # pages in memory to find those slabs.
    #
    for page in for_each_page(sdb.get_prog()):
        try:
            if not page.flags & pg_slab_flag:
                continue
        except drgn.FaultError:
            #
            # Not 100% sure why this happens but we've verified
            # in multiple cases that we've been able to detect
            # all the slabs/pages from all the caches and none
            # of them fall into these segments that give us
            # FaultErrors. One hypothesis of why these occur
            # is because the regions that we've tried to get
            # rid from where origininally all zeros and they
            # where subsequently filtered out. Another one is
            # that these regions are just not mapped to anything.
            # In any case this scenario hasn't brought up any
            # issues with the functionality that we are trying
            # to provide.
            #
            continue

        slab_cache = page.slab_cache
        if slab_cache.value_() == 0x0:
            continue
        if slab_cache != cache and slab_cache.value_() not in cache_children:
            continue

        free_set: Set[int] = set()
        if page.value_() in cache_partials:
            try:
                free_set = {
                    obj.value_()
                    for obj in for_each_freeobj_in_slab(cache, page)
                }
            except drgn.FaultError as err:
                #
                # It is common for freelists of partials slabs to be
                # updated while we are looking at them. Instead of
                # stopping right away or going though and reading
                # more invalid data we just skip to the next slab.
                #
                print(
                    f"inconsistent freelist address:{hex(err.address)} page:{hex(page)}"
                )
                continue
        addr = page_to_virt(page) + cache_red_left_padding(cache)
        obj_size = slab_cache.size
        num_objects = page.objects
        end = addr + (num_objects * obj_size)

        p = addr
        while p < end:
            if p.value_() not in free_set:
                yield p
            p += obj_size
