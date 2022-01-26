#
# Copyright 2019 Delphix
# Copyright 2021 Datto, Inc.
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

import drgn
from drgn.helpers.linux.list import list_for_each
import sdb
from sdb.commands.linux.process import Process


class Mutex(sdb.PrettyPrinter):
    """
    DESCRIPTION

    Display the owner of a mutex and its waiters.

    EXAMPLES (some output shortened)

    sdb> spa |member spa_activities_lock | member m_mutex | mutex
    owner of mutex 0xffff925f36005eb8:
    --------------------------------
    PID: 13205 zpool scrub tank

    #0 at 0xffffffff90d79914 (__schedule+0x394/0xa53) in context_switch at ../core.c:3551:2
    #1 at 0xffffffff90d79914 (__schedule+0x394/0xa53) in __schedule at ../core.c:4312:8
    #2 at 0xffffffff90d7a035 (schedule+0x55/0xba) in schedule at ../kernel/sched/core.c:4387:3
    #3 at 0xffffffff90d7a406 (io_schedule+0x16/0x3a) in io_schedule at ../kernel/sched/core.c:6029:2
    #4 at 0xffffffffc09246ff (cv_wait_common+0xef/0x297) in cv_wait_common at ../spl-condvar.c:144:3
    #5 at 0xffffffffc09248e8 (__cv_wait_io+0x18/0x1a) in __cv_wait_io at ../spl/spl-condvar.c:178:2
    #6 at 0xffffffffc0be06b3 (txg_wait_synced_impl+0xf3/0x258) in txg_wait_synced_impl at ..
    #7 at 0xffffffffc0be0830 (txg_wait_synced+0x10/0x3b) in txg_wait_synced at ../txg.c:736:2
    #8 at 0xffffffffc0b93d72 (dsl_sync_task_common+0x1c2/0x296) in dsl_sync_task_common at ..
    #9 at 0xffffffffc0b93e6a (dsl_sync_task+0x1a/0x1c) in dsl_sync_task at ../dsl_synctask.c:132:10
    #10 at 0xffffffffc0b91206 (dsl_scan+0x96/0x123) in dsl_scan at ../dsl_scan.c:853:10
    #11 at 0xffffffffc0bbeaf1 (spa_scan+0x81/0x1c0) in spa_scan at ../spa.c:8037:10
    #12 at 0xffffffffc0c37a80 (zfs_ioc_pool_scan+0x60/0xd1) in zfs_ioc_pool_scan at zfs_ioctl.c:1691
    #13 at 0xffffffffc0c413b9 (zfsdev_ioctl_common+0x609/0x6b7) in zfsdev_ioctl_common at ..
    #14 at 0xffffffffc0c7c477 (zfsdev_ioctl+0x57/0xdf) in zfsdev_ioctl at ../zfs/module/zfs/..
    #15 at 0xffffffff9050349d (ksys_ioctl+0x9d/0xc2) in vfs_ioctl at ../fs/ioctl.c:48:10 (inlined)
    #16 at 0xffffffff9050349d (ksys_ioctl+0x9d/0xc2) in ksys_ioctl at ../fs/ioctl.c:753:11
    #17 at 0xffffffff905034ea (__x64_sys_ioctl+0x1a/0x1e) in __do_sys_ioctl at ../fs/ioctl.c:762:9
    #18 at 0xffffffff905034ea (__x64_sys_ioctl+0x1a/0x1e) in __se_sys_ioctl at ../fs/ioctl.c:760:1
    #19 at 0xffffffff905034ea (__x64_sys_ioctl+0x1a/0x1e) in __x64_sys_ioctl at ../fs/ioctl.c:760:1
    #20 at 0xffffffff90d6cb89 (do_syscall_64+0x49/0xb6) in do_syscall_64 at ..
    #21 at 0xffffffff90e0008c (entry_SYSCALL_64+0x7c/0x156) at ../arch/x86/entry/entry_64.S:117
    --------------------------------


    waiters on mutex 0xffff925f36005eb8:
    --------------------------------
    PID: 13156

    #0 at 0xffffffff90d79914 (__schedule+0x394/0xa53) in context_switch at ../core.c:3551
    #1 at 0xffffffff90d79914 (__schedule+0x394/0xa53) in __schedule at ../core.c:4312:8
    #2 at 0xffffffff90d7a035 (schedule+0x55/0xba) in schedule at ../core.c:4387:3
    #3 at 0xffffffff90d7a33e (schedule_preempt_disabled+0xe/0x10) in schedule_preempt_disabled at ..
    #4 at 0xffffffff90d7bf1d (__mutex_lock.isra.0+0x17d/0x4e0) in __mutex_lock_common at ..
    #5 at 0xffffffff90d7bf1d (__mutex_lock.isra.0+0x17d/0x4e0) in __mutex_lock at ..
    #6 at 0xffffffff90d7c293 (__mutex_lock_slowpath+0x13/0x15) in __mutex_lock_slowpath at ..
    #7 at 0xffffffff90d7c2d2 (mutex_lock+0x32/0x36) in mutex_lock at ../kernel/locking/mutex.c:284:3
    #8 at 0xffffffffc0bc5a35 (spa_notify_waiters+0x35/0x9b) in spa_notify_waiters at ../spa.c:9546:2
    #9 at 0xffffffffc0b8ce8b (dsl_process_async_destroys+0x21b/0x73a) in dsl_process_async_destroys
    #10 at 0xffffffffc0b92e63 (dsl_scan_sync+0x1e3/0xb70) in dsl_scan_sync at ../dsl_scan.c:3571:8
    #11 at 0xffffffffc0bc040a (spa_sync_iterate_to_convergence+0x13a/0x317) in spa_sync_iterate..
    #12 at 0xffffffffc0bc0bc2 (spa_sync+0x2f2/0x872) in spa_sync at ../zfs/module/zfs/spa.c:9269:2
    #13 at 0xffffffffc0be14d7 (txg_sync_thread+0x2a7/0x3de) in txg_sync_thread at ../txg.c:591:3
    #14 at 0xffffffffc092ec94 (thread_generic_wrapper+0x84/0xbc) in thread_generic_wrapper at ..
    #15 at 0xffffffff902c18f4 (kthread+0x114/0x146) in kthread at ../kernel/kthread.c:291:9
    #16 at 0xffffffff90204482 (ret_from_fork+0x22/0x2d) at ../arch/x86/entry/entry_64.S:293
    --------------------------------

    """

    names = ["mutex"]
    input_type = "struct mutex *"
    output_type = "struct mutex *"
    MUTEX_FLAGS = 0x07

    def pretty_print(self, objs: drgn.Object) -> None:
        for mtx in objs:
            # see __mutex_owner() in kernel/locking/mutex.c
            print(f"owner of mutex {hex(int(mtx))}:")
            if mtx.owner.counter != 0:
                contents = sdb.get_prog().read_u64(mtx.owner.address_of_())
                own_addr = int(contents) & ~self.MUTEX_FLAGS
                own_task = sdb.create_object('struct task_struct *', own_addr)
                Process(own_task.pid).print_process()
            else:
                print("NULL")

            # waiters
            print(f"waiters on mutex {hex(int(mtx))}:")
            for obj in list_for_each(mtx.wait_list.address_of_()):
                sw = drgn.cast('struct semaphore_waiter *', obj)
                Process(sw.task.pid).print_process()
