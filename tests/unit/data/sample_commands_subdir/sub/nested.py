"""Nested command in a subdirectory."""

from typing import Iterable

import drgn
import sdb


class Nested(sdb.Command):
    """Nested test command in sub-directory."""

    names = ["nested_ext"]
    load_on = [sdb.All()]

    def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        return objs
