Creating and loading external commands
======================================

sdb is designed to be extended.  You can write your own commands as Python
modules, load them at startup or at runtime, and they integrate seamlessly
with the pipeline, tab completion, and ``help`` system.

Anatomy of a command
--------------------

An sdb command is a Python class that inherits from :class:`sdb.Command` (or
one of its subclasses) and declares a ``names`` list.  When the module is
imported, ``Command.__init_subclass__`` automatically registers the class.

Here is a minimal command that prints the ``comm`` field of every
``task_struct`` it receives:

.. code-block:: python

   from typing import ClassVar, Iterable, List, Optional

   import drgn
   import sdb


   class TaskName(sdb.Command):
       """Print the name of each task."""

       names: ClassVar[List[str]] = ["task_name"]
       input_type: ClassVar[Optional[str]] = "struct task_struct *"
       load_on: ClassVar[List[sdb.Runtime]] = [sdb.Kernel()]

       def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
           for task in objs:
               print(task.comm.string_().decode())
           return iter(())

Key attributes:

``names``
   A list of strings.  Each string becomes a name you can type in the REPL.
   The first name is the primary name used in help text.

``input_type``
   The C type this command expects as input (as a string).  Set to ``None``
   if the command accepts any type.  When a pointer type is declared, sdb
   will automatically cast ``void *`` inputs and take the address of
   non-pointer objects of the matching type.

``load_on``
   Controls when the command is registered.  Use ``sdb.Kernel()`` for
   kernel-only commands, ``sdb.Userland()`` for userland, or ``sdb.All()``
   to always register.  You can also use ``sdb.Module("zfs")`` or
   ``sdb.Library("libfoo")`` for finer control (these currently resolve to
   kernel and userland respectively until drgn gains module enumeration).


Choosing a base class
---------------------

sdb provides several base classes; pick the one that matches your command's
purpose:

:class:`sdb.Command`
   Generic base.  Implement ``_call(self, objs)`` and yield drgn objects
   or print output.  For a simple example, see
   `count.py <https://github.com/sdimitro/sdb/blob/master/sdb/commands/count.py>`_.

:class:`sdb.SingleInputCommand`
   Like ``Command``, but calls ``_call_one(self, obj)`` for each input
   object independently.  If one object triggers a ``FaultError``, the
   error is printed and processing continues with the next object.  See
   `member.py <https://github.com/sdimitro/sdb/blob/master/sdb/commands/member.py>`_
   for an example.

:class:`sdb.Walker`
   Iterate over a data structure.  Declare ``input_type`` and implement
   ``walk(self, obj)`` to yield each element.  For a real example, see the
   ``linux_list`` walker in
   `linked_lists.py <https://github.com/sdimitro/sdb/blob/master/sdb/commands/linux/linked_lists.py>`_
   or the AVL tree walker in
   `avl.py <https://github.com/sdimitro/sdb/blob/master/sdb/commands/spl/avl.py>`_.

:class:`sdb.PrettyPrinter`
   Human-readable output.  Declare ``input_type`` and implement
   ``pretty_print(self, objs)``.  When the command is last in a pipeline
   it prints; otherwise it yields objects.

:class:`sdb.Locator`
   Find objects of a given type.  Declare ``output_type`` and implement
   ``no_input(self)`` for when the command starts a pipeline.  Locators
   can also be combined with ``PrettyPrinter`` to create commands that
   both locate and display objects.  The ``stacks`` command in
   `stacks.py <https://github.com/sdimitro/sdb/blob/master/sdb/commands/linux/stacks.py>`_
   is a good example of a hybrid Locator + PrettyPrinter, and the ``spa``
   command in
   `spa.py <https://github.com/sdimitro/sdb/blob/master/sdb/commands/zfs/spa.py>`_
   shows Locator with ``@InputHandler`` dispatch.


Example: a Walker
-----------------

.. code-block:: python

   from typing import ClassVar, Iterable, List, Optional

   import drgn
   import sdb


   class MyListWalker(sdb.Walker):
       """Walk a custom linked list."""

       names: ClassVar[List[str]] = ["my_list"]
       input_type: ClassVar[Optional[str]] = "struct my_list_head *"
       load_on: ClassVar[List[sdb.Runtime]] = [sdb.Module("my_module")]

       def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
           node = obj.first
           while not sdb.is_null(node):
               yield node
               node = node.next

Once loaded, this walker is available through the ``walk`` dispatch command::

   sdb> addr some_global | walk


Example: a Locator + PrettyPrinter
-----------------------------------

.. code-block:: python

   from typing import ClassVar, Iterable, List, Optional

   import drgn
   import sdb


   class GizmoInfo(sdb.Locator, sdb.PrettyPrinter):
       """Locate and pretty-print gizmo_t objects."""

       names: ClassVar[List[str]] = ["gizmo"]
       input_type: ClassVar[Optional[str]] = "gizmo_t *"
       output_type: ClassVar[Optional[str]] = "gizmo_t *"
       load_on: ClassVar[List[sdb.Runtime]] = [sdb.Kernel()]

       def no_input(self) -> Iterable[drgn.Object]:
           head = sdb.get_object("gizmo_list")
           node = head.first
           while not sdb.is_null(node):
               yield node
               node = node.next

       def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
           for obj in objs:
               name = obj.name.string_().decode()
               print(f"{hex(obj.value_())}  {name}")

Usage::

   sdb> gizmo
   0xffff...  widget-alpha
   0xffff...  widget-beta

   sdb> gizmo | count
   (unsigned long long)2


Adding arguments
----------------

Override ``_init_parser`` to add argparse arguments:

.. code-block:: python

   import argparse

   class TaskName(sdb.Command):
       names: ClassVar[List[str]] = ["task_name"]
       input_type: ClassVar[Optional[str]] = "struct task_struct *"
       load_on: ClassVar[List[sdb.Runtime]] = [sdb.Kernel()]

       @classmethod
       def _init_parser(cls, name: str) -> argparse.ArgumentParser:
           parser = super()._init_parser(name)
           parser.add_argument("-u", "--upper", action="store_true",
                               help="uppercase the output")
           return parser

       def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
           for task in objs:
               name = task.comm.string_().decode()
               if self.args.upper:
                   name = name.upper()
               print(name)
           return iter(())

The arguments are parsed automatically and available as ``self.args``.
Users see them in ``help``::

   sdb> help task_name
   SUMMARY
       task_name [-h] [-u]
   ...


Loading external commands
-------------------------

There are four ways to load your commands:

At startup via CLI flag
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   sudo sdb --load-commands /path/to/my/commands

The path can be a single ``.py`` file or a directory (all ``.py`` files
are loaded recursively, skipping ``__init__.py`` and friends).  The flag
can be repeated.

At startup via environment variable
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   export SDB_COMMANDS_PATH="/path/one:/path/two"
   sudo sdb

Colon-separated, just like ``$PATH``.

At runtime from the REPL
^^^^^^^^^^^^^^^^^^^^^^^^^

::

   sdb> %load-commands /path/to/my/commands
   Loaded 2 command(s): task_name, gizmo

Tab completion is automatically refreshed after loading.

From the library API
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import sdb

   sdb.start(prog, command_paths=["/path/to/my/commands"])

Or load after initialization:

.. code-block:: python

   sdb.load_external_commands("/path/to/my/commands")
   sdb.register_commands()


File layout tips
----------------

* Keep one command per file, or group related commands in one file.
* Do **not** name your file ``__init__.py`` or start it with ``__`` -- these
  are skipped by the loader.
* Imports of ``sdb`` and ``drgn`` work normally -- sdb is already in the
  Python path.
* If your commands have heavy dependencies, put them behind lazy imports
  inside ``_call`` to avoid slowing down startup.
