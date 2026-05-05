Quickstart
==========

Installation
------------

From PyPI
^^^^^^^^^

.. code-block:: bash

   pip install sdb-debugger

From source
^^^^^^^^^^^

Dependencies:

* Python 3.10+
* `drgn <https://github.com/osandov/drgn>`_
* `libkdumpfile <https://github.com/ptesarik/libkdumpfile>`_ (optional --
  needed for kdump-compressed crash dumps)

.. note::

   For drgn to support kdump files it must be *compiled* with libkdumpfile.
   Install libkdumpfile **before** installing drgn.

.. code-block:: bash

   git clone https://github.com/sdimitro/sdb.git
   cd sdb
   pip install .

For development (editable install with linters and test dependencies):

.. code-block:: bash

   pip install -e ".[dev]"


Attaching to a target
---------------------

Live kernel (default):

.. code-block:: bash

   sudo sdb

Running process:

.. code-block:: bash

   sudo sdb -p <PID>

Crash dump or core dump:

.. code-block:: bash

   sdb <vmlinux | binary> <dump>

Evaluate a single command and exit:

.. code-block:: bash

   sudo sdb -e "stacks | count"


First commands
--------------

Once inside the REPL you can start exploring immediately::

   sdb> find_task 1 | member comm
   (char [16])"systemd"

   sdb> find_task 1 | stack
   TASK_STRUCT        STATE             COUNT
   ==========================================
   0xffff89cea441dd00 INTERRUPTIBLE         1
                     __schedule+0x2e5
                     schedule+0x33
                     schedule_hrtimeout_range_clock+0xfd
                     schedule_hrtimeout_range+0x13
                     ep_poll+0x40a
                     do_epoll_wait+0xb7
                     __x64_sys_epoll_wait+0x1e
                     do_syscall_64+0x57
                     entry_SYSCALL_64+0x7c


Pipes
-----

sdb commands are composed using the ``|`` operator, just like a Unix shell.
Each command receives drgn objects from the command before it and yields drgn
objects to the next::

   sdb> threads | filter obj.comm == "kworker/0:0" | stack

The pipeline flows left to right.  Some commands (called *Locators*) can
start a pipeline by producing objects on their own -- ``threads``, ``stacks``,
``slabs``, ``spa``, and many others work this way.

To pipe sdb output into a **shell command**, use ``!``::

   sdb> addr modules | lxlist "struct module" list | member name ! sort | head -n 3
   (char [56])"aesni_intel"
   (char [56])"async_memcpy"
   (char [56])"async_pq"

Everything after ``!`` is passed to ``/bin/sh``, so standard Unix tools like
``sort``, ``head``, ``grep``, ``wc``, etc. all work.


Entering the pipeline: ``echo`` and ``addr``
---------------------------------------------

Not every pipeline starts from a Locator.  Two commands let you inject objects
into the pipeline manually:

``addr``
   Resolve a symbol name or hex address to a drgn object.  This is the primary
   way to start a pipeline from a global variable::

      sdb> addr jiffies
      *(volatile unsigned long *)0xffffffff97205000 = 4901248625

      sdb> addr jiffies | deref
      (volatile unsigned long)4905392949

   Multiple symbols can be given at once::

      sdb> addr jiffies slab_caches 0xffffdeadbeef

``echo``
   Create a ``void *`` from a raw numeric address::

      sdb> echo 0xffff9d0adbe2c000 | cast spa_t * | member spa_name
      (char [256])"rpool"


Casting
-------

When a command expects a specific pointer type, sdb automatically casts
``void *`` inputs.  You can also cast explicitly::

   sdb> echo 0xffff9d0adbe2c000 | cast spa_t *

This is useful when starting from a raw address found in a log or another
tool.  The ``cast`` command accepts any C type expression that drgn can
resolve.


Getting help
------------

Every command has built-in help accessible from the REPL:

.. code-block:: none

   sdb> help stacks
   SUMMARY
       stacks [-h] [-a] [-v] [-l] [-c FUNCTION] [-m MODULE] [-t TSTATE]

       Print the stack traces for active threads (task_struct)
   ...

``help`` and ``man`` are aliases for the same command.

To list all registered walkers and their types::

   sdb> walk


mdb compatibility syntax
------------------------

If you are coming from illumos/Solaris and are used to mdb, sdb understands
the ``symbol::cmd`` shorthand::

   sdb> spa_namespace_avl::walk

This is automatically transformed to ``addr spa_namespace_avl | walk`` before
execution.  Inside a pipeline the leading ``::`` is simply stripped::

   sdb> spa | ::member spa_name

becomes ``spa | member spa_name``.

mdb compatibility is enabled by default.  Disable it with ``--no-mdb-compat``
if it ever conflicts with something::

   $ sudo sdb --no-mdb-compat
