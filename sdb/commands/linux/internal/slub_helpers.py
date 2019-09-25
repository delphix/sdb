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


def is_root_cache(obj: drgn.Object) -> bool:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    return obj.memcg_params.root_cache.value_() == 0x0


def list_for_each_root_cache(prog: drgn.Program) -> Iterable[drgn.Object]:
    yield from list_for_each_entry("struct kmem_cache",
                                   prog["slab_root_caches"].address_of_(),
                                   "memcg_params.__root_caches_node")


def list_for_each_child_cache(root_cache: drgn.Object) -> Iterable[drgn.Object]:
    assert root_cache.type_.type_name() == 'struct kmem_cache *'
    yield from list_for_each_entry(
        "struct kmem_cache", root_cache.memcg_params.children.address_of_(),
        "memcg_params.children_node")


def nr_slabs(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    nslabs = obj.node[0].nr_slabs.counter.value_()
    if not is_root_cache(obj):
        return nslabs
    for child in list_for_each_entry("struct kmem_cache",
                                     obj.memcg_params.children.address_of_(),
                                     "memcg_params.children_node"):
        nslabs += nr_slabs(child)
    return nslabs


def entries_per_slab(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    return obj.oo.x.value_() & 0xffff


def entry_size(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    return obj.size.value_()


def object_size(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    return obj.object_size.value_()


def memused(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    nslabs = nr_slabs(obj)
    epslab = entries_per_slab(obj)
    esize = entry_size(obj)
    return nslabs * epslab * esize


def objs(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    count = obj.node[0].total_objects.counter.value_()
    if not is_root_cache(obj):
        return count
    for child in list_for_each_entry("struct kmem_cache",
                                     obj.memcg_params.children.address_of_(),
                                     "memcg_params.children_node"):
        count += objs(child)
    return count


def inactive_objs(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    node = obj.node[0].partial
    free = 0
    for page in list_for_each_entry("struct page", node.address_of_(), "lru"):
        free += page.objects.value_() - page.inuse.value_()

    if not is_root_cache(obj):
        return free

    for child in list_for_each_entry("struct kmem_cache",
                                     obj.memcg_params.children.address_of_(),
                                     "memcg_params.children_node"):
        free += inactive_objs(child)
    return free


def active_objs(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    return objs(obj) - inactive_objs(obj)


def util(obj: drgn.Object) -> int:
    assert obj.type_.type_name() == 'struct kmem_cache *'
    total = objs(obj)
    if total == 0:
        return 0
    inactive = inactive_objs(obj)
    return int(((total - inactive) / total) * 100)
