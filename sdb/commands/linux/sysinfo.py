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

import re
from typing import Iterable, Optional

import drgn

import sdb


class Kcmdline(sdb.Command):
    """
    Print the kernel boot command line (equivalent of /proc/cmdline).

    EXAMPLES
        sdb> kcmdline
        vmlinuz root=UUID=2862ac0d... ro console=tty0 ...
    """

    names = ["kcmdline"]
    load_on = [sdb.Kernel()]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        prog = sdb.get_prog()
        cmdline = prog["saved_command_line"].string_().decode()
        print(cmdline)
        return None


class SerialNumber(sdb.Command):
    """
    Print the host DMI product serial number.

    DESCRIPTION
        Reads from the kernel's ``dmi_ident`` table
        (``DMI_PRODUCT_SERIAL``).  Falls back to extracting
        ``systemd.hostname=`` from the kernel command line if DMI
        data is unavailable.

    EXAMPLES
        sdb> serial_number
        Serial: ss943425x5108570
    """

    names = ["serial_number"]
    load_on = [sdb.Kernel()]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Optional[Iterable[drgn.Object]]:
        prog = sdb.get_prog()

        try:
            idx = prog.constant("DMI_PRODUCT_SERIAL")
        except LookupError:
            idx = 7

        try:
            serial = prog["dmi_ident"][idx]
            if serial:
                print(f"Serial: {serial.string_().decode()}")
                return None
        except (KeyError, AttributeError, drgn.FaultError):
            pass

        cmdline = prog["saved_command_line"].string_().decode()
        m = re.search(r"systemd\.hostname=(\S+)", cmdline)
        if m:
            print(f"Serial (from hostname): {m.group(1)}")
        else:
            print("Serial number not available")
        return None
