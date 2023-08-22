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

import argparse
from typing import Iterable

import drgn
from drgn.helpers.linux.printk import get_printk_records
import sdb

# pylint: disable=line-too-long


class DMesg(sdb.Command):
    """
    DESCRIPTION

        Get contents from kernel log buffer formatted like dmesg(1).

    EXAMPLES

        sdb> dmesg ! tail
        [   30.544756] AVX2 version of gcm_enc/dec engaged.
        [   30.545019] AES CTR mode by8 optimization enabled
        [   38.855043] Rounding down aligned max_sectors from 4294967295 to 4294967288
        [   38.863427] db_root: cannot open: /etc/target
        [   39.822443] aufs 5.15.5-20211129
        [   40.344495] NFSD: Using UMH upcall client tracking operations.
        [   40.344501] NFSD: starting 20-second grace period (net f0000000)
        [   40.978893] EXT4-fs (zd0): mounted filesystem with ordered data mode. Opts: (null). Quota mode: none.
        [  176.825888] bpfilter: Loaded bpfilter_umh pid 4662
        [  176.826272] Started bpfilter

        sdb> dmesg -l 3
        [   38.863427] db_root: cannot open: /etc/target
    """

    names = ["dmesg"]
    # input_type = None
    load_on = [sdb.Kernel()]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        #
        # #define KERN_EMERG	KERN_SOH "0"	/* system is unusable */
        # #define KERN_ALERT	KERN_SOH "1"	/* action must be taken immediately */
        # #define KERN_CRIT	KERN_SOH "2"	/* critical conditions */
        # #define KERN_ERR	KERN_SOH "3"	/* error conditions */
        # #define KERN_WARNING	KERN_SOH "4"	/* warning conditions */
        # #define KERN_NOTICE	KERN_SOH "5"	/* normal but significant condition */
        # #define KERN_INFO	KERN_SOH "6"	/* informational */
        # #define KERN_DEBUG	KERN_SOH "7"	/* debug-level messages */
        #
        parser.add_argument('--level', '-l', nargs="?", type=int, default=7)
        return parser

    def _call(self, objs: Iterable[drgn.Object]) -> None:
        for record in get_printk_records(sdb.get_prog()):
            if self.args.level >= record.level:
                secs = record.timestamp // 1000000000
                sub_secs = record.timestamp % 1000000000 // 1000
                msg = record.text.decode('utf-8')
                print(f"[{secs: 5d}.{sub_secs:06d}] {msg}")
