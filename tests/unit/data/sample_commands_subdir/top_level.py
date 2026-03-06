"""Top-level command in a nested directory structure."""

from typing import Iterable

import drgn
import sdb


class TopLevel(sdb.Command):
    """Top-level test command in nested dir."""

    names = ["top_level_ext"]
    load_on = [sdb.All()]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        return objs
