#
# Copyright 2020 Delphix
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
from typing import Iterable, List, Optional

import drgn
import drgn.helpers.linux.cpumask as drgn_cpumask
import drgn.helpers.linux.percpu as drgn_percpu
import sdb


class LxPerCpuPtr(sdb.SingleInputCommand):
    """
    Return the per-CPU pointer for the given CPU (or all if none is specified).

    EXAMPLES
        Get the per-CPU data of the "kmalloc-8" kmem cache for CPUs 0 and 1:

            sdb> slabs | filter obj.name == "kmalloc-8" | member cpu_slab
            (struct kmem_cache_cpu *)0x2f040
            sdb> slabs | filter obj.name == "kmalloc-8" | member cpu_slab | percpu 0
            (struct kmem_cache_cpu *)0xffff944effc2f040
            sdb> slabs | filter obj.name == "kmalloc-8" | member cpu_slab | percpu 1
            (struct kmem_cache_cpu *)0xffff944effd2f040
            sdb> slabs | filter obj.name == "kmalloc-8" | member cpu_slab | percpu 0 1
            (struct kmem_cache_cpu *)0xffff944effc2f040
            (struct kmem_cache_cpu *)0xffff944effd2f040
    """

    names = ["percpu"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("cpus", nargs="*", type=int)
        return parser

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.ncpus = len(
            list(drgn_cpumask.for_each_possible_cpu(sdb.get_prog())))

    def _call_one(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        cpus = self.args.cpus
        if not cpus:
            cpus = range(self.ncpus)
        for cpu in cpus:
            if cpu >= self.ncpus:
                raise sdb.CommandError(
                    self.name,
                    f"available CPUs [0-{self.ncpus -1}] - requested CPU {cpu}")
            yield drgn_percpu.per_cpu_ptr(obj, cpu)


class LxPerCpuCounterSum(sdb.SingleInputCommand):
    """
    Return the sum of a per-CPU counter.

    EXAMPLES
        Get the global memory commitment made in a system (this is almost the
        same as calling vm_memory_committed() on the kernel C code):

            sdb> addr vm_committed_as | cpu_counter_sum
            (s64)1067887

        Get the number of orphaned TCP sockets:

            sdb> addr tcp_orphan_count | cpu_counter_sum
            (s64)0

        Get the number of allocated TCP sockets:

            sdb> addr tcp_sockets_allocated | cpu_counter_sum
            (s64)58
    """

    names = ["cpu_counter_sum"]
    input_type = "struct percpu_counter *"

    def _call_one(self, obj: drgn.Object) -> Iterable[drgn.Object]:
        try:
            sum_ = drgn_percpu.percpu_counter_sum(obj)
        except AttributeError as err:
            raise sdb.CommandError(self.name,
                                   "input is not a percpu_counter") from err
        yield drgn.Object(sdb.get_prog(), type="s64", value=sum_)
