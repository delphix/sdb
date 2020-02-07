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
from typing import Iterable

import drgn
import sdb


class PType(sdb.Command):
    """
    Print the type passed as an argument.

    EXAMPLES
        Resolve spa_t typedef:

            sdb> ptype spa_t
            typedef struct spa spa_t

        Print the members of the spa and vdev structures:

            sdb> ptype spa vdev
            struct spa {
                    char spa_name[256];
                    char *spa_comment;
                    ...
            }
            struct vdev {
                    uint64_t vdev_id;
                    uint64_t vdev_guid;
                    ...
            }

        Print enums and unions:

            sdb> ptype zfs_case v_t thread_union
            enum zfs_case {
                    ZFS_CASE_SENSITIVE = 0,
                    ZFS_CASE_INSENSITIVE = 1,
                    ZFS_CASE_MIXED = 2,
            }
            typedef union {
                    iv_t e;
                    uint8_t b[8];
            } v_t
            union thread_union {
                    struct task_struct task;
                    unsigned long stack[2048];
            }
    """

    names = ["ptype"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("type", nargs="*", metavar="<type>")
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        for tp_name in self.args.type:
            found = False

            #
            # There is a reason we have "" at the end below after we
            # check all the C keywords below. There are cases that
            # we've seen in C codebases that do things like this:
            #
            #   typedef union GCObject GCObject; // taken from LUA repo
            #
            # If we checked for typedefs first (e.g. "" below), then
            # we'd get the description that is useless:
            #
            #   sdb> ptype GCObject
            #   typedef union GCObject GCObject
            #
            # Putting the typedef at the end allows to first check for
            # the real type info which is more useful:
            #
            #   sdb> ptype GCObject
            #   union GCObject {
            #   	GCheader gch;
            #   	union TString ts;
            #           ...
            #   }
            #
            # In the future we probably want to also support queries
            # like `ptype union GCObject` so the code doesn't have
            # to be mindful of this issue.
            #
            for prefix in ["struct ", "enum ", "union ", ""]:
                try:
                    print(sdb.get_prog().type(f"{prefix}{tp_name}"))
                    found = True
                except LookupError:
                    pass
                if found:
                    break
            if not found:
                raise sdb.CommandError(
                    self.name,
                    f"couldn't find typedef, struct, enum, nor union named '{tp_name}'"
                )
