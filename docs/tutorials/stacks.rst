Using ``stacks``
================

The ``stacks`` command (alias ``stack``) is one of the most frequently used
commands when debugging Linux kernels.  It prints aggregated stack traces for
kernel threads, making it easy to spot patterns, find blocked threads, and
diagnose hangs.

Basic usage
-----------

With no arguments, ``stacks`` iterates over every ``task_struct`` in the
system, groups threads by identical call stacks, and prints them sorted by
frequency (most common first)::

   sdb> stacks
   TASK_STRUCT        STATE             COUNT
   ==========================================
   0xffff9521bb3c3b80 IDLE                394
                     __schedule+0x24e
                     schedule+0x2c
                     worker_thread+0xba
                     kthread+0x121
                     ret_from_fork+0x35

   0xffff9521bb3cbb80 INTERRUPTIBLE       384
                     __schedule+0x24e
                     schedule+0x2c
                     smpboot_thread_fn+0x166
                     kthread+0x121
                     ret_from_fork+0x35
   ...


Reading the output
------------------

Each group has a header and a stack trace:

**TASK_STRUCT**
   The address of one representative ``struct task_struct *`` for this group.
   You can pipe it into other commands (e.g. ``member comm`` to get the
   thread name).

**STATE**
   The scheduler state of the threads in this group.  Common values:

================= ==============================================
State             Meaning
================= ==============================================
RUNNING           On a CPU or in the run queue
INTERRUPTIBLE     Sleeping, wakes on signals or events
UNINTERRUPTIBLE   Sleeping, does not wake on signals (D state)
IDLE              Idle kernel worker
STOPPED           Stopped by a signal (SIGSTOP)
ZOMBIE            Exited, waiting for parent to reap
PARKED            Parked kthread (cpu hotplug)
================= ==============================================

**COUNT**
   How many threads share this exact (state, stack) combination.  A high
   count for an UNINTERRUPTIBLE stack is a strong signal that something is
   blocked.

The stack trace itself lists frames from the sleep/block point at the top
down to the entry point at the bottom (``ret_from_fork`` for kthreads,
``entry_SYSCALL_64`` for syscalls).


Filtering by thread state
--------------------------

Use ``-t`` to show only threads in a particular state::

   sdb> stacks -t RUNNING
   TASK_STRUCT        STATE             COUNT
   ==========================================
   0xffff95214ff31dc0 RUNNING               1

   sdb> stacks -t UNINTERRUPTIBLE

You can also use the single-character shortcuts from ``ps(1)``: ``R``, ``S``,
``D``, ``T``, ``I``, etc.::

   sdb> stacks -t D


Filtering by function
---------------------

Use ``-c`` to show only threads whose stack contains a specific function::

   sdb> stacks -c l2arc_feed_thread
   TASK_STRUCT        STATE             COUNT
   ==========================================
   0xffff9521b3f43b80 INTERRUPTIBLE         1
                     __schedule+0x24e
                     schedule+0x2c
                     schedule_timeout+0x15d
                     __cv_timedwait_common+0xdf
                     __cv_timedwait_sig+0x16
                     l2arc_feed_thread+0x66
                     thread_generic_wrapper+0x74
                     kthread+0x121
                     ret_from_fork+0x35


Filtering by kernel module
--------------------------

Use ``-m`` to show only threads that have at least one frame from a given
kernel module::

   sdb> stacks -m zfs
   TASK_STRUCT        STATE             COUNT
   ==========================================
   0xffff952130515940 INTERRUPTIBLE         1
                     __schedule+0x24e
                     schedule+0x2c
                     cv_wait_common+0x11f
                     __cv_wait_sig+0x15
                     zthr_procedure+0x51
                     thread_generic_wrapper+0x74
                     kthread+0x121
                     ret_from_fork+0x35
   ...


Listing all threads per stack
-----------------------------

By default only one representative ``task_struct`` address is shown per
group.  Use ``-a`` to list every thread::

   sdb> stacks -a -t IDLE
   TASK_STRUCT        STATE
   ==========================================
   0xffff9521bb3c3b80 IDLE
   0xffff9521bb3c7b80
   0xffff9521bb3cbb80
   ...


Composing with other commands
-----------------------------

Because ``stacks`` is both a **Locator** and a **PrettyPrinter**, it can
appear anywhere in a pipeline:

Count ZFS threads::

   sdb> stacks -m zfs | count
   (unsigned long long)12

Get the ``comm`` (name) of all uninterruptible threads::

   sdb> stacks -t D | member comm

Feed specific threads into ``stack``::

   sdb> threads | filter obj.comm == "zthr_procedure" | stack

Pipe to the shell to post-process::

   sdb> stacks ! grep -c "UNINTERRUPTIBLE"


Practical scenarios
-------------------

Diagnosing a hang
^^^^^^^^^^^^^^^^^

When a system is unresponsive, start with::

   sdb> stacks -t D

Every UNINTERRUPTIBLE stack is a thread waiting for something (I/O, a lock,
etc.).  If many threads share the same stack, that common point is likely
the bottleneck.  Follow up with ``-c <function>`` to narrow down.

Crash dump triage
^^^^^^^^^^^^^^^^^

For crash dumps, find the panicking thread first::

   sdb> crashed_thread
   TASK_STRUCT        STATE             COUNT
   ==========================================
   0xffff8f15d7333d00 RUNNING               1
                     __crash_kexec+0x9d
                     ...

Then look at the broader picture with ``stacks`` to see what else was
happening at the time of the crash.

Slow or stuck I/O
^^^^^^^^^^^^^^^^^^

A high thread count on an I/O-related stack trace is a strong indicator that
I/Os are either hanging or completing too slowly.  For example, if you see
dozens of threads piled up in a block-layer or storage-driver wait path,
that subsystem is likely the bottleneck.  Combine ``-m`` with ``-c`` to
confirm::

   sdb> stacks -m nvme -c nvme_queue_rq

If the count keeps growing across successive ``stacks`` invocations on a
live system, the I/Os are not completing at all (hung).  If the count is
high but stable, throughput is simply too low for the workload.

Finding threads from a specific subsystem
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Combine ``-m`` and ``-c`` to zero in::

   sdb> stacks -m zfs -c spa_sync

This shows only threads in the ZFS module whose stack includes
``spa_sync``.
