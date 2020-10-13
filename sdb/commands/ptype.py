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
from sdb.commands.internal import util


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

            sdb> ptype zfs_case 'struct v' thread_union
            enum zfs_case {
                    ZFS_CASE_SENSITIVE = 0,
                    ZFS_CASE_INSENSITIVE = 1,
                    ZFS_CASE_MIXED = 2,
            }
            struct v {
                    uint8_t b[16];
            }
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
        for tname in self.args.type:
            print(util.get_valid_type_by_name(self, tname))
