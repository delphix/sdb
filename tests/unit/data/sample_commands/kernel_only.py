"""Sample command that only loads on kernel targets."""

from typing import Iterable

import drgn
import sdb


class KernelOnly(sdb.Command):
    """Test command restricted to kernel runtime."""

    names = ["kernel_only_ext"]
    load_on = [sdb.Kernel()]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        return objs
