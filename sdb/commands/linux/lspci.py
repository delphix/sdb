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

from typing import Callable, Dict, Iterable, Iterator, Union

import drgn
from drgn.helpers.linux.list import list_for_each_entry

import sdb
from sdb.commands.internal.table import Table


def _iter_all_pci_devs(prog: drgn.Program) -> Iterator[drgn.Object]:
    """Walk pci_root_buses -> children recursively."""

    def _walk_bus(bus: drgn.Object) -> Iterator[drgn.Object]:
        yield from list_for_each_entry("struct pci_dev",
                                       bus.devices.address_of_(), "bus_list")
        for child in list_for_each_entry("struct pci_bus",
                                         bus.children.address_of_(), "node"):
            yield from _walk_bus(child)

    for root in list_for_each_entry("struct pci_bus",
                                    prog["pci_root_buses"].address_of_(),
                                    "node"):
        yield from _walk_bus(root)


def _bdf(dev: drgn.Object) -> str:
    bus_nr = int(dev.bus.number)
    devfn = int(dev.devfn)
    return f"{bus_nr:04x}:{devfn >> 3:02x}.{devfn & 7}"


def _pci_class(dev: drgn.Object) -> str:
    try:
        return f"{int(dev.member_('class')):06x}"
    except (AttributeError, LookupError):
        return "??????"


def _driver_name(dev: drgn.Object) -> str:
    try:
        drv_ptr = dev.dev.driver.value_()
        if drv_ptr:
            return dev.dev.driver.name.string_().decode()
    except (AttributeError, drgn.FaultError):
        pass
    return ""


class Lspci(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate and print PCI devices (like lspci(8)).

    DESCRIPTION
        Walks ``pci_root_buses`` recursively and yields every
        ``struct pci_dev`` in the system.  When used at the end
        of a pipeline, prints a table with BDF address, vendor,
        device, class code, and bound driver name.

    EXAMPLES
        List all PCI devices:

            sdb> lspci
            BDF       VEN  DEV  CLASS  DRIVER
            --------- ---- ---- ------ -------------
            0000:00.0 8086 7190 060000 agpgart-intel
            0000:07.1 8086 7111 01018a ata_piix
            0003:00.0 15ad 07b0 020000 vmxnet3
            ...

        Filter to VMware devices (vendor 0x15ad):

            sdb> lspci | filter 'obj.vendor == 0x15ad' | lspci
            BDF       VEN  DEV  CLASS  DRIVER
            --------- ---- ---- ------ --------
            0000:07.7 15ad 0740 088000 vmw_vmci
            0000:0f.0 15ad 0405 030000 vmwgfx
            0003:00.0 15ad 07b0 020000 vmxnet3
            ...
    """

    names = ["lspci"]
    input_type = "struct pci_dev *"
    output_type = "struct pci_dev *"
    load_on = [sdb.Kernel()]

    FIELDS: Dict[str, Callable[[drgn.Object], Union[str, int]]] = {
        "BDF": _bdf,
        "VEN": lambda obj: f"{int(obj.vendor):04x}",
        "DEV": lambda obj: f"{int(obj.device):04x}",
        "CLASS": _pci_class,
        "DRIVER": _driver_name,
    }

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        fields = list(Lspci.FIELDS.keys())
        table = Table(fields, None, {"BDF": str})
        for dev in objs:
            row = {f: Lspci.FIELDS[f](dev) for f in fields}
            table.add_row(row["BDF"], row)
        table.print_()

    def no_input(self) -> Iterable[drgn.Object]:
        yield from _iter_all_pci_devs(sdb.get_prog())
