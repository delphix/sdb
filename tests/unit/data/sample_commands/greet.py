"""Another sample external command for testing the plugin loader."""

from typing import Iterable

import drgn
import sdb


class Greet(sdb.Command):
    """Second test command -- used by loader unit tests."""

    names = ["greet_ext"]
    load_on = [sdb.All()]

    def _call(self,
              objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        return objs
