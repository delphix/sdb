Using sdb as a library
======================

sdb is not just a standalone debugger -- it exposes a Python API that lets
you embed an sdb REPL inside your own tool or run sdb pipelines
programmatically.  A real-world example of this is GhostWire, a remote
kernel introspection tool for NVIDIA BlueField DPUs that builds a
``drgn.Program`` backed by TCP (or RDMA) memory reads and then drops the
user into sdb.

.. contents:: In this tutorial
   :local:
   :depth: 2


The ``sdb.start()`` entry point
--------------------------------

The simplest integration is to hand sdb a ``drgn.Program`` and let it run
the REPL:

.. code-block:: python

   import drgn
   import sdb

   prog = drgn.Program()
   prog.set_kernel()
   prog.load_default_debug_info()

   sdb.start(prog)

``sdb.start()`` accepts several optional parameters:

.. code-block:: python

   sdb.start(
       prog,
       command_paths=["/path/to/my/commands"],  # extra command directories
       prompt="mydb> ",                          # custom REPL prompt
       pre_cmd_hook=my_refresh_fn,               # called before each command
       eval_cmd="stacks | count",                # run one command and exit
       history_file="~/.mydb_history",           # readline history path
   )


Running pipelines programmatically
-----------------------------------

For scripting and automation, use ``sdb.invoke()`` to execute a pipeline
and iterate over the results:

.. code-block:: python

   import sdb

   # After sdb.start() has been called or the target has been
   # set up manually (see "Manual setup" below)

   for obj in sdb.invoke([], "spa | member spa_name"):
       name = obj.string_().decode()
       print(f"Pool: {name}")

``invoke`` returns a generator of ``drgn.Object`` values.  The first
argument is the initial input to the pipeline (an empty list to start from
scratch).

You can also build and execute pipelines at a lower level:

.. code-block:: python

   from sdb.pipeline import execute_pipeline
   from sdb.command import get_registered_commands

   cmds = get_registered_commands()
   pipeline = [cmds["spa"]([], "spa"), cmds["count"]([], "count")]
   pipeline[0].isfirst = True
   pipeline[-1].islast = True

   for obj in execute_pipeline([], pipeline):
       print(obj)


The ``pre_cmd_hook`` pattern
----------------------------

Many tools that embed sdb maintain caches or transport state that must be
refreshed between commands.  The ``pre_cmd_hook`` parameter solves this.

It accepts any callable with no arguments.  sdb calls it immediately before
evaluating each REPL command (but **not** for meta-commands like
``%session``).

A typical pattern for remote debuggers:

.. code-block:: python

   sdb.start(
       prog,
       command_paths=[sdb_commands_dir],
       prompt="sdb[remote]> ",
       pre_cmd_hook=transport.bump_generation,
   )

The effect: each new command sees fresh host memory, while reads within a
single command's execution are cached for performance.

Typical use cases:

* Invalidating a memory cache so each command sees fresh data.
* Reconnecting a transport layer if the connection was dropped.
* Refreshing authentication tokens for a remote target.
* Logging or telemetry (count commands, measure latency).


Loading custom commands
-----------------------

Pass directories or files containing your ``sdb.Command`` subclasses via
``command_paths``:

.. code-block:: python

   sdb.start(prog, command_paths=[
       "/opt/mytools/sdb_commands",
       "/home/me/debug/my_walkers.py",
   ])

You can also load commands after initialization:

.. code-block:: python

   sdb.load_external_commands("/opt/mytools/sdb_commands")
   sdb.register_commands()

See :doc:`external-commands` for how to write custom commands.


Manual setup (without ``sdb.start()``)
---------------------------------------

If you need tighter control -- for example to run pipelines without starting
a REPL -- you can set up the sdb runtime manually:

.. code-block:: python

   import drgn
   import sdb
   import sdb.target as sdb_target

   prog = drgn.Program()
   prog.set_kernel()
   prog.load_default_debug_info()

   sdb_target.set_prog(prog)
   sdb_target.set_thread(next(prog.threads()).object)
   sdb_target.set_frame(-1)

   sdb.register_commands()

   # Now you can call invoke() directly
   for obj in sdb.invoke([], "slabs | head 3"):
       print(obj)


Real-world example: GhostWire
-------------------------------

GhostWire is a remote Linux kernel introspection tool that runs on an
NVIDIA BlueField DPU.  It reads the host machine's physical memory over the
network (using TCP or RDMA), constructs a ``drgn.Program`` from those remote
reads, and then offers the user either a plain drgn REPL or a full sdb
session.

The interesting part is how the remote ``drgn.Program`` is built.
GhostWire's transport layer provides a ``read_phys(address, size)`` function
that fetches physical memory from the host over the network.  The program
construction looks roughly like this:

.. code-block:: python

   import drgn

   # 1. Read vmcoreinfo from the host (needed for KASLR and type info)
   vmcoreinfo = transport.read_phys(host.vmcoreinfo_phys, host.vmcoreinfo_size)

   # 2. Create a Program with the host's platform and vmcoreinfo
   prog = drgn.Program(
       platform=drgn.Platform(drgn.Architecture.X86_64),
       vmcoreinfo=vmcoreinfo,
   )

   # 3. Register physical memory segments backed by the network transport
   read_fn = transport.make_drgn_read_fn()
   for r in host.ranges:
       prog.add_memory_segment(
           address=r.start,
           size=r.end - r.start,
           read_fn=read_fn,
           physical=True,
       )

   # 4. Initialize kernel page-table walking and KASLR relocation
   prog.set_linux_kernel_custom(vmcoreinfo=vmcoreinfo, is_live=True)

   # 5. Load debug info (vmlinux with DWARF)
   prog.main_module("vmlinux", create=True).try_file("/path/to/vmlinux")

At this point ``prog`` is a fully functional ``drgn.Program`` that resolves
types, walks page tables, and reads kernel memory -- all transparently
backed by network reads.  The user doesn't need to know or care that the
data comes from a remote machine.

The sdb integration is then just a thin bridge:

.. code-block:: python

   import os
   import sdb

   def run_sdb(prog, transport):
       sdb_commands_dir = os.path.join(
           os.path.dirname(__file__), "sdb_commands"
       )
       sdb.start(
           prog,
           command_paths=[sdb_commands_dir],
           prompt="sdb[gw]> ",
           pre_cmd_hook=transport.bump_generation,
       )

Key points:

* **``command_paths``** loads GhostWire-specific commands from a directory
  next to the bridge module.
* **``pre_cmd_hook``** bumps the transport cache generation so each REPL
  command sees fresh host memory.  GhostWire uses a generation-based page
  cache: reads within a single command are cached (for fast page-table
  walks), but the cache is invalidated between commands.
* **``prompt``** is customized to ``sdb[gw]>`` so the user knows they are
  in a GhostWire sdb session.
* sdb is an **optional dependency** -- GhostWire imports it lazily and only
  when the user passes ``--sdb``.

GhostWire also adds its own domain-specific commands.  For example, a
command to print the host's firmware version:

.. code-block:: python

   from typing import ClassVar, Iterable, List

   import drgn
   import sdb


   class GwFirmwareVersion(sdb.Command):
       """Print the firmware version from the kernel command line."""

       names: ClassVar[list[str]] = ["gw_firmware_version"]
       load_on: ClassVar[list[sdb.Runtime]] = [sdb.Kernel()]

       def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
           cmdline = sdb.get_object("saved_command_line").string_().decode()
           for part in cmdline.split():
               if part.startswith("fw_ver="):
                   print(part.split("=", 1)[1])
                   break
           else:
               print("firmware version not found in command line")
           return iter(())

This demonstrates how an embedding tool can expose its own domain-specific
commands through sdb's REPL while reusing the entire sdb infrastructure --
pipelines, tab completion, help, recording, and everything else come for
free.
