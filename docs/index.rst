===
sdb
===

**The Slick/Simple Debugger** -- a pipeline-based debugger for Linux kernel
and userland, built on `drgn <https://drgn.readthedocs.io/>`_.

sdb attaches to a live kernel, a running process, or a crash/core dump and
provides a composable set of commands connected by pipes::

   sdb> stacks -m zfs | count
   (unsigned long long)12

   sdb> find_task 1 | member comm
   (char [16])"systemd"

   sdb> spa | member spa_name ! sort
   (char [256])"data"
   (char [256])"rpool"

Features
--------

* **50+ built-in commands** for Linux kernel internals, ZFS, and SPL data
  structures.
* **Pipeline architecture** -- compose commands with ``|`` and pipe to the
  shell with ``!``.
* **Session recording** -- capture memory accesses into a portable vmcore
  and replay offline.
* **Extensible** -- write your own commands in Python and load them at
  runtime.
* **Library API** -- embed sdb in your own tools (see
  :doc:`tutorials/library-usage`).
* **mdb compatibility** -- use the familiar ``symbol::cmd`` syntax.


.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   tutorials/stacks
   tutorials/recording
   tutorials/external-commands
   tutorials/library-usage

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference/concepts
   reference/api
   reference/commands
   reference/developer-notes

.. toctree::
   :maxdepth: 1
   :caption: Project

   changelog
