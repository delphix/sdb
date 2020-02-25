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

#
# The pylint workaround below is for the example
# sections of the help messages.
#
# pylint: disable=line-too-long

import argparse
from typing import Iterable

import drgn
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.list import hlist_for_each_entry

import sdb
from sdb.commands.internal.util import get_valid_struct_name


class LxList(sdb.Command):
    """
    Walk a standard Linux doubly-linked list

    DESCRIPTION
        Given the type of its nodes and the name of its list_node
        member, walk a doubly-linked list as defined in the Linux
        kernel ('struct list_head' type in include/linux/list.h).

    EXAMPLES
        Walk all modules in the system:

            sdb> addr modules | lxlist module list | member name ! head -n 3
            (char [56])"connstat"
            (char [56])"rpcsec_gss_krb5"
            (char [56])"nfsv4"
            ...

        Walk all root caches of SLUB:

            sdb> addr slab_root_caches | lxlist kmem_cache memcg_params.__root_caches_node | member name
            (const char *)0xffff90cc010ae620 = "nfs_direct_cache"
            (const char *)0xffff90cbdfb96a90 = "nfs_read_data"
            (const char *)0xffff90cbdfb96650 = "nfs_inode_cache"
            (const char *)0xffff90cbd9983e60 = "t10_pr_reg_cache"
            ...

    """

    names = ["linux_list", "lxlist"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "struct_name",
            help="name of the struct used for entries in the list")
        parser.add_argument("member",
                            help="name of the node member within the struct")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        sname = get_valid_struct_name(self, self.args.struct_name)
        for obj in objs:
            try:
                yield from list_for_each_entry(sname, obj, self.args.member)
            except LookupError as err:
                raise sdb.CommandError(self.name, str(err))


class LxHList(sdb.Command):
    """
    Walk a standard Linux hash-table list

    DESCRIPTION
        Given the type of its nodes and the name of its hlist_node
        member, walk a hash-table list as defined in the Linux
        kernel ('struct hlist_head' type in include/linux/list.h).

    EXAMPLES
        Walk the list of task_structs that use the same PID as the
        initial task:

            sdb> addr init_task | member thread_pid.tasks[3] | lxhlist task_struct pid_links[3] | member comm
            (char [16])"idle_inject/0"
            (char [16])"migration/0"
            (char [16])"rcu_sched"
            (char [16])"ksoftirqd/0"
            ...

    """

    names = ["linux_hlist", "lxhlist"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "struct_name",
            help="name of the struct used for entries in the list")
        parser.add_argument("member",
                            help="name of the node member within the struct")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        sname = get_valid_struct_name(self, self.args.struct_name)
        for obj in objs:
            try:
                yield from hlist_for_each_entry(sname, obj, self.args.member)
            except LookupError as err:
                raise sdb.CommandError(self.name, str(err))


def is_list_empty(l: drgn.Object) -> bool:
    """
    True if list is empty, False otherwise.
    """
    assert sdb.type_canonical_name(l.type_) == 'struct list_head'
    return int(l.address_of_().value_()) == int(l.next.value_())
