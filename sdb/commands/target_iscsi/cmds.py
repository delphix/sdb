#
# Copyright 2023 Delphix
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
# pylint: disable=line-too-long

import argparse
import socket
from typing import Iterable

import drgn
import sdb
from sdb.commands.internal.util import removeprefix
from sdb.commands.linux.linked_lists import LxList


def sockaddr_get_port(sockaddr: drgn.Object) -> int:
    AF_INET = 2
    AF_INET6 = 10

    if sockaddr.ss_family == AF_INET:
        sa_in = drgn.cast("struct sockaddr_in *", sockaddr.address_of_())
        return int(socket.ntohs(int(sa_in.sin_port)))
    if sockaddr.ss_faimly == AF_INET6:
        raise ValueError("printing of IPv6 addresses is not implemented yet")
    raise ValueError("unexpected socket address type")


class IscsiNetworkPortals(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate all iSCSI Target Network Portals

    EXAMPLES
        Print all network portals

            sdb> iscsi_portals
            ADDRESS            THREAD_STATE   PORT EXPORTS
            ----------------------------------------------
            0xffff978acaa70600       ACTIVE   3260       1

        Print the stack trace of the first network portal thread

            sdb> iscsi_portals | head 1 | member np_thread | stack
            TASK_STRUCT        STATE             COUNT
            ==========================================
            0xffff978a85ec9780 INTERRUPTIBLE         1
                              __schedule+0x2de
                              __schedule+0x2de
                              schedule+0x42
                              schedule_timeout+0x10e
                              inet_csk_accept+0x271
                              inet_csk_accept+0x271
                              inet_accept+0x45
                              kernel_accept+0x59
                              iscsit_accept_np+0x38
                              __iscsi_target_login_thread+0xe7
                              iscsi_target_login_thread+0x24
                              kthread+0x104
                              ret_from_fork+0x1f
    """

    names = ["iscsi_portals"]
    input_type = "struct iscsi_np *"
    output_type = "struct iscsi_np *"

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        print(
            f"\033[4m{'ADDRESS':<18} {'THREAD_STATE':>12} {'PORT':>6} {'EXPORTS':>7}\033[0m"
        )
        for np in objs:
            port = sockaddr_get_port(np.np_sockaddr)
            tstate = removeprefix(np.np_thread_state.format_(type_name=False),
                                  "ISCSI_NP_THREAD_")
            print(
                f"{hex(np):18} {tstate:>12} {port:>6} {int(np.np_exports):>7}")

    def no_input(self) -> drgn.Object:
        yield from sdb.execute_pipeline(
            [sdb.get_object("g_np_list").address_of_()],
            [
                LxList(["struct iscsi_np", "np_list"]),
                sdb.Cast(["struct iscsi_np *"])
            ],
        )


class Tiqn(sdb.Locator, sdb.PrettyPrinter):
    """
    Locate all iSCSI Target IQNs

    EXAMPLES
        Print all iSCSI Target IQNs on the system

        ADDRESS            TIQN
        -----------------------
        0xffff978a7f778000 iqn.2003-01.org.linux-iscsi.dlpx-60stage-qar-67247-27a4593a.x8664:sn.bc4d2ca129d5
    """

    names = ["tiqn"]
    input_type = "struct iscsi_tiqn *"
    output_type = "struct iscsi_tiqn *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("indices", type=int, nargs="*")
        return parser

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        print(f"\033[4m{'ADDRESS':<18} TIQN\033[0m")
        for tiqn in objs:
            tiqn_name = tiqn.tiqn.format_(type_name=False).strip('\"')
            print(f'{hex(tiqn):18} {tiqn_name}')

    def no_input(self) -> drgn.Object:
        tiqns = sdb.execute_pipeline(
            [sdb.get_object("g_tiqn_list").address_of_()],
            [
                LxList(["struct iscsi_tiqn", "tiqn_list"]),
                sdb.Cast(["struct iscsi_tiqn *"])
            ],
        )
        for tiqn in tiqns:
            if (self.args.indices and tiqn.tiqn_index not in self.args.indices):
                continue
            yield tiqn


class TiqnStats(sdb.PrettyPrinter):
    """
    Print iSCSI Target IQN statistics given an TIQN.

    EXAMPLES

        sdb> tiqn | head 1 | tiqn_info
        iqn.2003-01.org.linux-iscsi.dlpx-60stage-qar-67247-27a4593a.x8664:sn.bc4d2ca129d5
                --- info ---
                        state: ACTIVE
                # of sessions: 3

                --- login stats ---
                             accepts: 3
                           redirects: 0
                 authorization fails: 0
                authentication fails: 0
                   negotiation fails: 0
                    misc login fails: 0

                --- logout stats ---
                  normal: 0
                abnormal: 0
    """

    names = ["tiqn_info"]
    input_type = "struct iscsi_tiqn *"

    def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
        for tiqn in objs:
            tiqn_name = tiqn.tiqn.format_(type_name=False).strip('\"')
            state = removeprefix(tiqn.tiqn_state.format_(type_name=False),
                                 "TIQN_STATE_")
            login_stats = tiqn.login_stats
            logout_stats = tiqn.logout_stats
            print(f"{tiqn_name}")
            print("\t--- info ---")
            print(f"\t        state: {state}")
            print(f"\t# of sessions: {int(tiqn.tiqn_nsessions)}")
            print()
            print("\t--- login stats ---")
            print(f"\t             accepts: {int(login_stats.accepts)}")
            print(f"\t           redirects: {int(login_stats.redirects)}")
            print(f"\t authorization fails: {int(login_stats.authorize_fails)}")
            print(
                f"\tauthentication fails: {int(login_stats.authenticate_fails)}"
            )
            print(f"\t   negotiation fails: {int(login_stats.negotiate_fails)}")
            print(f"\t    misc login fails: {int(login_stats.other_fails)}")
            print()
            print("\t--- logout stats ---")
            print(f"\t  normal: {int(logout_stats.normal_logouts)}")
            print(f"\tabnormal: {int(logout_stats.abnormal_logouts)}")
