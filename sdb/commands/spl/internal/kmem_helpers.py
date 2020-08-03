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
import drgn.helpers.linux.list as drgn_list
import drgn.helpers.linux.percpu as drgn_percpu

import sdb
from sdb.commands.internal import p2
from sdb.commands.linux import linked_lists
from sdb.commands.linux.internal import slub_helpers as slub


def for_each_spl_kmem_cache() -> Iterable[drgn.Object]:
    yield from drgn_list.list_for_each_entry(
        "spl_kmem_cache_t",
        sdb.get_object("spl_kmem_cache_list").address_of_(), "skc_list")


def backed_by_linux_cache(cache: drgn.Object) -> bool:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return int(cache.skc_linux_cache.value_()) != 0x0


def slab_name(cache: drgn.Object) -> str:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return str(cache.skc_name.string_().decode('utf-8'))


def nr_slabs(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return int(cache.skc_slab_total.value_())


def slab_alloc(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return int(cache.skc_slab_alloc.value_())


def slab_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return int(cache.skc_slab_size.value_())


def slab_linux_cache_source(cache: drgn.Object) -> str:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    if not backed_by_linux_cache(cache):
        name = slab_name(cache)
        subsystem = "SPL"
    else:
        name = cache.skc_linux_cache.name.string_().decode('utf-8')
        subsystem = "SLUB"
    return f"{name}[{subsystem:4}]"


def for_each_slab_flag_in_cache(cache: drgn.Object) -> Iterable[str]:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    flag = cache.skc_flags.value_()
    for enum_entry, enum_entry_bit in cache.prog_.type(
            'enum kmc_bit').enumerators:
        if flag & (1 << enum_entry_bit):
            yield enum_entry.replace('_BIT', '')


def slab_flags(cache: drgn.Object) -> str:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return '|'.join(for_each_slab_flag_in_cache(cache))


def object_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return int(cache.skc_obj_size.value_())


def nr_objects(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    if backed_by_linux_cache(cache):
        return obj_alloc(cache)
    return int(cache.skc_obj_total.value_())


def obj_alloc(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    if backed_by_linux_cache(cache):
        try:
            return int(drgn_percpu.percpu_counter_sum(cache.skc_linux_alloc))
        except AttributeError:
            #
            # The percpu_counter referenced above wasn't in ZoL until the
            # following commit: ec1fea4516ac2f0c08d31d6308929298d1b281d0
            #
            # Fall back to the old-mechanism of using skc_obj_alloc if that
            # percpu_counter member doesn't exist (an AttributeError will
            # be thrown).
            #
            pass
    return int(cache.skc_obj_alloc.value_())


def obj_inactive(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return nr_objects(cache) - obj_alloc(cache)


def objs_per_slab(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return int(cache.skc_slab_objs.value_())


def entry_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    if backed_by_linux_cache(cache):
        return slub.entry_size(cache.skc_linux_cache)
    ops = objs_per_slab(cache)
    if ops == 0:
        return 0
    return int(slab_size(cache) / objs_per_slab(cache))


def active_memory(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    return obj_alloc(cache) * entry_size(cache)


def total_memory(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    if backed_by_linux_cache(cache):
        return slub.total_memory(cache.skc_linux_cache)
    return slab_size(cache) * nr_slabs(cache)


def util(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    total_mem = total_memory(cache)
    if total_mem == 0:
        return 0
    return int((active_memory(cache) / total_mem) * 100)


def sko_from_obj(cache: drgn.Object, obj: drgn.Object) -> drgn.Object:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    cache_obj_align = cache.skc_obj_align.value_()
    return sdb.create_object(
        'spl_kmem_obj_t *',
        obj.value_() + p2.p2roundup(object_size(cache), cache_obj_align))


def spl_aligned_obj_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    cache_obj_align = cache.skc_obj_align.value_()
    spl_obj_type_size = sdb.type_canonicalize_size('spl_kmem_obj_t')
    return p2.p2roundup(object_size(cache), cache_obj_align) + p2.p2roundup(
        spl_obj_type_size, cache_obj_align)


def spl_aligned_slab_size(cache: drgn.Object) -> int:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    cache_obj_align = cache.skc_obj_align.value_()
    spl_slab_type_size = sdb.type_canonicalize_size('spl_kmem_slab_t')
    return p2.p2roundup(spl_slab_type_size, cache_obj_align)


def for_each_onslab_object_in_slab(slab: drgn.Object) -> Iterable[drgn.Object]:
    assert sdb.type_canonical_name(slab.type_) == 'struct spl_kmem_slab *'
    cache = slab.sks_cache
    sks_size = spl_aligned_slab_size(cache)
    spl_obj_size = spl_aligned_obj_size(cache)

    for i in range(slab.sks_objs.value_()):
        obj = sdb.create_object('void *',
                                slab.value_() + sks_size + (i * spl_obj_size))
        #
        # If the sko_list of the object is empty, it means that
        # this object is not part of the slab's internal free list
        # and therefore it is allocated. NOTE: sko_list in the
        # actual code is not a list, but a link on a list. Thus,
        # the check below is not checking whether the "object
        # list" is empty for this slab, but rather whether the
        # link is part of any list.
        #
        sko = sko_from_obj(cache, obj)
        assert sko.sko_magic.value_() == 0x20202020  # SKO_MAGIC
        if linked_lists.is_list_empty(sko.sko_list):
            yield obj


def for_each_object_in_spl_cache(cache: drgn.Object) -> Iterable[drgn.Object]:
    assert sdb.type_canonical_name(cache.type_) == 'struct spl_kmem_cache *'
    #
    # ZFSonLinux initially implemented OFFSLAB caches for certain cases
    # that never showed up and thus have never been used in practice.
    # Ensure here that we are not looking at such a cache.
    #
    if 'KMC_OFFSLAB' in list(for_each_slab_flag_in_cache(cache)):
        raise sdb.CommandError("spl_caches",
                               "KMC_OFFSLAB caches are not supported")

    for slab_list in [cache.skc_complete_list, cache.skc_partial_list]:
        for slab in drgn_list.list_for_each_entry("spl_kmem_slab_t",
                                                  slab_list.address_of_(),
                                                  "sks_list"):
            yield from for_each_onslab_object_in_slab(slab)
