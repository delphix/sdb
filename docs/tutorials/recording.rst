Recording and replaying sessions
================================

sdb can record the memory accesses made during a debugging session into a
portable vmcore file.  This file can later be replayed on any machine --
without the original crash dump, live kernel, or even root access -- making
it easy to share debugging context with colleagues or revisit a session
offline.

.. contents:: In this tutorial
   :local:
   :depth: 2


How it works
------------

When recording is active, sdb intercepts every memory read that drgn performs
and stores the data in a sparse memory buffer.  Reads are "fat-aligned" to
256-byte boundaries so that surrounding memory (like struct fields you haven't
explicitly accessed yet) is captured too.

When recording stops, the buffer is written out as a standard ELF64 vmcore
(or optionally a kdump-compressed file) using `kdumpling
<https://pypi.org/project/kdumpling/>`_.  The vmcore includes:

* All memory segments that were read during the session.
* The kernel's ``vmcoreinfo`` (needed for KASLR relocation and type info).
* An SDB-specific ELF note with session metadata (timestamp, kernel release,
  etc.).

Because the output is a real vmcore, it can be loaded by drgn, crash, or any
other tool that reads ELF core dumps.


Starting a recording
--------------------

From the command line
^^^^^^^^^^^^^^^^^^^^^

Pass ``--record`` when launching sdb::

   $ sudo sdb --record my-session

sdb will start normally and save the recording to
``my-session.vmcore.recorded`` when you exit (or Ctrl-D).

From the REPL
^^^^^^^^^^^^^

Start recording at any time during a session::

   sdb> %session record my-session
   Recording started. Output: my-session.vmcore.recorded

Now run whatever commands you need.  Every memory access they trigger will
be captured.


Stopping a recording
--------------------

::

   sdb> %session stop
   Recording stopped.
   Saved to: my-session.vmcore.recorded
     Memory segments: 1842
     Memory size: 471552 bytes

If you started with ``--record``, the recording also stops automatically
when the REPL exits.


Checking recording status
-------------------------

::

   sdb> %session status
   Recording to: my-session.vmcore.recorded
     Format: elf
     Memory segments: 1842
     Memory size: 471552 bytes


Capturing extra data
--------------------

By default, only memory accessed by the commands you run is recorded.  Two
meta-commands let you explicitly pull in additional data:

``%session snapshot``
^^^^^^^^^^^^^^^^^^^^^

Capture an object and (optionally) follow its pointers::

   sdb> %session snapshot jiffies
   Snapshot captured: jiffies
     Memory segments: 1843
     Memory size: 471808 bytes

   sdb> %session snapshot init_task --depth 2

The ``--depth`` flag controls how many levels of pointer indirection to
follow (default 1).

``%session record-memory``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Capture a raw memory region by address and size::

   sdb> %session record-memory 0xffffffff97205000 4096
   Recorded 4096 bytes at 0xffffffff97205000

An optional ``--physical`` flag reads physical memory instead of virtual.


Configuring the output format
-----------------------------

By default, recordings are saved as uncompressed ELF vmcores.  For large
sessions you can switch to kdump format with compression::

   sdb> %session config format kdump
   Output format set to: kdump
     Compression: zlib

   sdb> %session config compression zstd
   Compression set to: zstd

   sdb> %session config compression-level 3
   Compression level set to: 3

Run ``%session config`` with no arguments to see the current settings.

Supported compression algorithms (kdump format only): ``none``, ``zlib``,
``lzo``, ``snappy``, ``zstd``.


Replaying a recorded session
-----------------------------

On the same machine or any other machine with sdb and the matching debug
symbols installed::

   $ sdb --replay my-session.vmcore.recorded -s /path/to/vmlinux

sdb opens the vmcore the same way it opens a crash dump -- no special
mode, no root access required.  The only limitation is that you can only
access memory that was captured during the original session.  Accessing
anything else will produce a ``FaultError``.

You can combine ``--replay`` with ``-e`` for scripted analysis::

   $ sdb --replay my-session.vmcore.recorded -s /path/to/vmlinux \
       -e "stacks -t D"


Recording whole memory regions
------------------------------

Sometimes you know you will need a particular memory region during replay
but haven't accessed it through normal commands yet.  The
``%session record-memory`` meta-command lets you capture arbitrary virtual
(or physical) address ranges into the recording::

   sdb> %session record-memory 0xffffffff97200000 0x10000
   Recorded 65536 bytes at 0xffffffff97200000

   sdb> %session record-memory 0x100000 0x1000 --physical
   Recorded 4096 bytes at 0x100000 (physical)

This is the low-level building block that ``%session snapshot`` builds on.
Use it when you need precise control over what gets captured -- for example,
recording a device's MMIO region or a specific page-table page.


Practical use cases
-------------------

Sharing debugging context
^^^^^^^^^^^^^^^^^^^^^^^^^

When triaging a production issue, one engineer can record a session and
share the ``.vmcore.recorded`` file.  A colleague can replay it without
needing access to the original system or crash dump -- they just need
the debug symbols.

Live dumps (local and remote)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Recording works on live kernels, not just crash dumps.  This means you can
create a "live dump" -- a lightweight snapshot of the kernel state you care
about -- without crashing the machine or taking a full memory dump.

This is especially powerful when sdb is embedded in a remote debugger.  A
tool like GhostWire can read a remote host's physical memory over the
network, and sdb's recording captures exactly the memory regions touched
during the remote session.  The resulting vmcore is fully self-contained
and can be replayed locally without any network access to the original host.

Offline analysis
^^^^^^^^^^^^^^^^

Record a session on a live system, then replay it later on your laptop::

   $ sudo sdb --record quick-look
   sdb> stacks
   sdb> slabs
   sdb> spa | pp
   ^D
   Recording saved to: quick-look.vmcore.recorded

   # later, on your laptop
   $ sdb --replay quick-look.vmcore.recorded -s ./vmlinux

Test cases and regression dumps
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Recorded sessions make excellent test fixtures.  When you encounter a bug
or an interesting kernel state, record a session that exercises it.  The
resulting vmcore becomes a deterministic, portable test input that can be
replayed in CI without needing the original hardware or a live kernel::

   $ sudo sdb --record regression-zfs-arc -e "arc"

Over time you build a library of recorded states covering edge cases that
would be difficult to reproduce on demand.  sdb's own integration tests
use crash dumps in exactly this way.

CI and automation
^^^^^^^^^^^^^^^^^

Use ``-e`` with ``--record`` to script a recording::

   $ sudo sdb --record nightly-check -e "stacks -t D | count"

The vmcore is saved even when using ``-e``, so you can archive it alongside
the command output for later inspection.
