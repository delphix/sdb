"""Sample external command for testing the plugin loader."""

from typing import Iterable

import drgn
import sdb


class Hello(sdb.Command):
    """Print a greeting -- used by loader unit tests."""

    names = ["hello_ext"]
    load_on = [sdb.All()]

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        return objs
