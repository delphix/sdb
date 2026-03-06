Command reference
=================

This page lists every built-in sdb command, grouped by domain.  Use
``help <command>`` inside the REPL for full details and examples.

.. contents:: On this page
   :local:
   :depth: 2


Core commands
-------------

These are defined in ``sdb/command.py`` and are always available.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **address**
     - ``addr``
     - Resolve symbol names or hex addresses to drgn objects; can start a
       pipeline.
   * - **cast**
     -
     - Cast pipeline objects to a specified C type.
   * - **deref**
     -
     - Dereference pointer objects.
   * - **walk**
     -
     - Dispatch to the appropriate Walker based on input type. With no input,
       lists all registered walkers.


General commands
----------------

Utility commands available for all target types.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **echo**
     - ``cc``
     - Create ``void *`` objects from raw numeric addresses.
   * - **member**
     -
     - Access struct members using ``.``, ``->``, or ``[]`` syntax.
   * - **filter**
     -
     - Filter objects by a Python expression (``obj`` refers to the current
       object).
   * - **pyfilter**
     -
     - Alias / variant of filter with Python expressions.
   * - **head**
     -
     - Pass through only the first *N* objects.
   * - **tail**
     -
     - Pass through only the last *N* objects.
   * - **count**
     - ``cnt``, ``wc``
     - Count objects in the pipeline and emit the result.
   * - **sum**
     -
     - Sum integer values in the pipeline.
   * - **type**
     -
     - Print the drgn type of each input object.
   * - **ptype**
     -
     - Print the type definition (struct layout, enum values, etc.).
   * - **sizeof**
     -
     - Print the size of a type in bytes.
   * - **container_of**
     -
     - Given a pointer to a struct member, find the containing struct.
   * - **array**
     -
     - Index into array objects.
   * - **print**
     -
     - Format output for scripts (machine-readable).
   * - **pretty_print**
     - ``pp``
     - Pretty-print objects using the registered PrettyPrinter for their type.
   * - **help**
     - ``man``
     - Show help for a command.
   * - **history**
     -
     - Show REPL command history.
   * - **exit**
     - ``quit``
     - Exit the REPL.


Linux kernel commands
---------------------

Available when debugging a kernel target (live or crash dump).

Threads and stacks
^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **threads**
     - ``thread``
     - Locate and print kernel threads (``task_struct``).
   * - **stacks**
     - ``stack``
     - Print aggregated stack traces for threads. Supports filtering by
       state (``-t``), function (``-c``), and module (``-m``).
   * - **crashed_thread**
     - ``panic_stack``, ``panic_thread``
     - Print the thread that panicked (crash dumps only).
   * - **trace**
     - ``bt``
     - Print a backtrace for a ``task_struct``.
   * - **stackframe**
     - ``frame``, ``f``
     - Select or print a stack frame for a task.
   * - **locals**
     - ``local``
     - Print local variables in the current stack frame.
   * - **registers**
     - ``register``
     - Print register values for a stack frame.

Processes
^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **find_task**
     -
     - Find a ``task_struct`` by PID.
   * - **pid**
     -
     - Find a ``struct pid`` by PID number.
   * - **fget**
     -
     - Get a ``struct file *`` from a file descriptor for a task.

Memory
^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **slabs**
     -
     - List slab caches (``kmem_cache``).
   * - **slub_cache**
     -
     - Walk objects in a SLUB slab cache.
   * - **percpu**
     -
     - Resolve a per-CPU pointer for a given CPU.
   * - **cpu_counter_sum**
     -
     - Sum a per-CPU counter across all CPUs.
   * - **whatis**
     -
     - Identify which kmem cache owns an address.

Data structure walkers
^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **linux_list**
     - ``lxlist``
     - Walk a ``struct list_head`` linked list.
   * - **linux_hlist**
     - ``lxhlist``
     - Walk a ``struct hlist_head`` hash list.
   * - **rbtree**
     -
     - Walk a red-black tree.

System
^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **dmesg**
     -
     - Print the kernel log buffer.


ZFS commands
------------

Available when the ZFS kernel module is loaded.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **spa**
     -
     - Locate and pretty-print SPA (Storage Pool Allocator) objects.
   * - **vdev**
     -
     - Walk and pretty-print vdevs in a pool.
   * - **metaslab**
     -
     - Walk metaslabs for a vdev.
   * - **zio**
     -
     - Iterate and pretty-print ZIO (ZFS I/O) objects.
   * - **dbuf**
     -
     - Iterate and pretty-print dbufs (DMU buffers).
   * - **arc**
     -
     - Print ARC (Adaptive Replacement Cache) statistics.
   * - **zfs_btree**
     -
     - Walk a ZFS B-tree.
   * - **blkptr**
     -
     - Pretty-print a ZFS block pointer.
   * - **range_tree**
     -
     - Pretty-print a range tree.
   * - **range_seg**
     -
     - Locate range segments from a range tree.
   * - **zfs_histogram**
     - ``zhist``
     - Print a ZFS histogram and its median.
   * - **zfs_dbgmsg**
     -
     - Print ZFS debug messages.


SPL commands
------------

Commands for the Solaris Porting Layer data structures.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Command
     - Aliases
     - Description
   * - **avl**
     -
     - Walk an AVL tree (``avl_tree_t``).
   * - **spl_list**
     -
     - Walk an SPL ``list_t``.
   * - **multilist**
     -
     - Walk a multilist.
   * - **spl_kmem_caches**
     -
     - List SPL kmem caches.
   * - **spl_cache**
     -
     - Walk objects in an SPL kmem cache.


Meta-commands
-------------

Meta-commands are prefixed with ``%`` and control the REPL itself rather
than operating on drgn objects.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Command
     - Description
   * - ``%load-commands <path>``
     - Load external sdb commands from a file or directory.
   * - ``%session record <file>``
     - Start recording memory accesses to ``<file>.vmcore.recorded``.
   * - ``%session stop``
     - Stop recording and save the vmcore.
   * - ``%session status``
     - Show recording/replay status and statistics.
   * - ``%session config [option] [value]``
     - Configure output format and compression.
   * - ``%session snapshot <var> [--depth N]``
     - Capture an object's memory into the recording.
   * - ``%session record-memory <addr> <size>``
     - Capture a raw memory region into the recording.
   * - ``%session load <file>``
     - Hint to use ``--replay`` for loading recorded sessions.
