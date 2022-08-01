#
# Copyright 2019 Delphix
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

from typing import Iterable

import drgn
import sdb


class DMesg(sdb.Locator, sdb.PrettyPrinter):

    names = ["dmesg"]

    input_type = "struct printk_log *"
    output_type = "struct printk_log *"

    def no_input(self) -> Iterable[drgn.Object]:
        log_idx = sdb.get_object("log_first_idx")
        log_seq = sdb.get_object("clear_seq")
        log_end = sdb.get_object("log_next_seq")
        log_buf = sdb.get_object("log_buf")

        while log_seq < log_end:
            entry = drgn.cast('struct printk_log *', log_buf + log_idx)

            yield entry

            if entry.len == 0:
                log_idx = 0
            else:
                log_idx += entry.len
            log_seq += 1

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        for obj in objs:
            secs = int(obj.ts_nsec.value_() / 1000000000)
            usecs = int((obj.ts_nsec.value_() % 1000000000) / 1000)

            message = drgn.cast("char *", obj) + obj.type_.type.size
            text = message.string_().decode('utf-8', 'ignore')

            print(f"[{secs:5d}.{usecs:06d}]: {text}")
