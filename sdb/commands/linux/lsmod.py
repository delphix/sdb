#
# Copyright 2026 CoreWeave
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

from typing import Callable, Dict, Iterable, Union

import drgn
from drgn.helpers.linux.list import list_for_each_entry

import sdb
from sdb.commands.internal.table import Table


def _module_size(mod: drgn.Object) -> int:
    """Extract module core size, handling kernel version differences."""
    try:
        return int(mod.core_layout.size)
    except AttributeError:
        pass
    try:
        num_types = sdb.get_prog().constant("MOD_MEM_NUM_TYPES")
        return sum(int(mod.mem[i].size) for i in range(num_types))
    except LookupError:
        return 0


class Lsmod(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate and print loaded kernel modules (like lsmod(8)).

    DESCRIPTION
        Walks the kernel's ``modules`` list and yields every
        ``struct module``.  When used at the end of a pipeline,
        prints a table with module name, size, reference count,
        and address.

    EXAMPLES
        List all loaded modules:

            sdb> lsmod
            MODULE                      SIZE REF ADDR
            ------------------------ ------- --- ------------------
            aes_x86_64                 20480   1 0xffffffffc0bbb1c0
            aesni_intel               372736   0 0xffffffffc0c0d400
            ...

        Filter modules by reference count:

            sdb> lsmod | filter 'obj.refcnt.counter > 1' | lsmod
            MODULE              SIZE REF ADDR
            ------------------ ----- --- ------------------
            async_memcpy        20480   2 0xffffffffc01ed080
            async_pq            24576   2 0xffffffffc022e140
            ...
    """

    names = ["lsmod"]
    input_type = "struct module *"
    output_type = "struct module *"
    load_on = [sdb.Kernel()]

    FIELDS: Dict[str, Callable[[drgn.Object], Union[str, int]]] = {
        "MODULE": lambda obj: obj.name.string_().decode(),
        "SIZE": _module_size,
        "REF": lambda obj: int(obj.refcnt.counter) - 1,
        "ADDR": lambda obj: hex(obj.value_()),
    }

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        fields = list(Lsmod.FIELDS.keys())
        table = Table(fields, {"SIZE", "REF"}, {"ADDR": str})
        for mod in objs:
            row = {f: Lsmod.FIELDS[f](mod) for f in fields}
            table.add_row(row["MODULE"], row)
        table.print_()

    def no_input(self) -> Iterable[drgn.Object]:
        modules = sdb.get_prog()["modules"]
        yield from list_for_each_entry("struct module", modules.address_of_(),
                                       "list")
