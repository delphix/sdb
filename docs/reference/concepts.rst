Core concepts
=============

This page explains the key abstractions that make sdb tick.  Understanding
these concepts will help you read sdb output, compose pipelines effectively,
and write your own commands.

The pipeline
------------

Every sdb expression is a **pipeline** of one or more commands separated by
``|``.  Data flows left to right as a stream of ``drgn.Object`` values:

.. code-block:: none

   ┌──────────┐     ┌────────┐     ┌────────┐
   │ Locator  │────▶│ Filter │────▶│ Pretty │
   │ (source) │     │        │     │ Printer│
   └──────────┘     └────────┘     └────────┘

The first command in a pipeline either:

* receives no input and produces objects on its own (a *Locator*), or
* receives objects from a manual source (``echo``, ``addr``).

The last command either:

* pretty-prints its input (if it is a *PrettyPrinter*), or
* formats each object using drgn's default ``format_()`` method.

Middle commands transform, filter, or walk the stream.

A pipeline can optionally end with ``! <shell command>`` to redirect sdb's
printed output into a Unix process::

   sdb> stacks | count ! tee /tmp/count.txt


Automatic type coercion
^^^^^^^^^^^^^^^^^^^^^^^^

When a command declares an ``input_type`` of ``foo_t *``, sdb automatically
handles two common mismatches:

1. **void \* → foo_t \***:  If the previous command yields ``void *``
   objects, sdb inserts an implicit ``cast foo_t *`` step.

2. **foo_t → foo_t \***:  If the previous command yields ``foo_t`` (the
   struct, not a pointer to it), sdb inserts an implicit ``address`` step
   to take its address.

This means you rarely need to cast manually -- just pipe things together and
sdb will do the right thing.


Command types
-------------

Every sdb command inherits from ``sdb.Command``.  Several specialised
subclasses exist, each with a different contract:

Command
^^^^^^^

The generic base class.  Subclasses implement:

.. code-block:: python

   def _call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
       ...

The method receives objects from the previous pipeline stage and yields
objects to the next.  It may also print output as a side effect.


SingleInputCommand
^^^^^^^^^^^^^^^^^^

Like ``Command``, but processes each input object independently.  Subclasses
implement:

.. code-block:: python

   def _call_one(self, obj: drgn.Object) -> Iterable[drgn.Object]:
       ...

If one object triggers a ``drgn.FaultError`` (invalid memory), sdb prints
the error and continues with the next object instead of aborting the entire
pipeline.  This is useful for commands that iterate over potentially stale
data structures.


Walker
^^^^^^

A command that iterates over a container data structure.  Subclasses declare
``input_type`` (e.g. ``"struct list_head *"``) and implement:

.. code-block:: python

   def walk(self, obj: drgn.Object) -> Iterable[drgn.Object]:
       ...

Walkers are registered in a global table keyed by their ``input_type``.
The ``walk`` dispatch command looks up the right walker automatically::

   sdb> addr slab_caches | walk

To see all registered walkers, run ``walk`` with no input::

   sdb> walk
   The following types have walkers:
       WALKER              TYPE
       lxlist              struct list_head *
       avl                 avl_tree_t *
       ...


PrettyPrinter
^^^^^^^^^^^^^

A command that produces human-readable output for a specific type.
Subclasses declare ``input_type`` and implement:

.. code-block:: python

   def pretty_print(self, objs: Iterable[drgn.Object]) -> None:
       ...

When a PrettyPrinter is the **last** command in a pipeline, sdb calls
``pretty_print()``.  When it is **not** last, it passes its input through
unchanged so downstream commands can continue processing.

The ``pp`` (pretty-print) command is a generic dispatcher -- it checks if a
PrettyPrinter exists for the input type and delegates to it.


Locator
^^^^^^^

A command that **finds** objects of a given type.  Subclasses declare
``output_type`` (the type being located) and implement:

.. code-block:: python

   def no_input(self) -> Iterable[drgn.Object]:
       ...

``no_input()`` is called when the Locator is the first command in a
pipeline (i.e. it has no upstream input).  It should yield all objects of
the located type.

A Locator can also accept input.  When it receives objects, it dispatches
to type-specific handlers registered with the ``@InputHandler`` decorator
(see :doc:`developer-notes`).  If no specific handler matches, the Locator
tries to use a Walker to iterate the input and cast each element to
``output_type``.

Many built-in commands (``spa``, ``stacks``, ``threads``, ``slabs``, etc.)
are **both** a Locator and a PrettyPrinter.  When used to start a pipeline
they locate objects; when used at the end they pretty-print them; and in the
middle they pass objects through.


Runtimes
--------

Commands declare when they should be loaded using the ``load_on`` attribute:

====================== ====================================================
Runtime                When the command is registered
====================== ====================================================
``sdb.All()``          Always (e.g. ``cast``, ``echo``, ``help``).
``sdb.Kernel()``       Only when debugging a kernel target.
``sdb.Userland()``     Only when debugging a userland process.
``sdb.Module(name)``   Currently equivalent to ``Kernel()`` -- intended
                       for kernel module-specific commands.
``sdb.Library(name)``  Currently equivalent to ``Userland()`` -- intended
                       for shared library-specific commands.
====================== ====================================================

This prevents kernel-only commands from appearing when you are debugging a
userland core, and vice versa.


``echo`` and ``addr`` -- entering the pipeline
-----------------------------------------------

Two built-in commands let you inject objects into a pipeline:

``echo`` (alias ``cc``)
   Creates a ``void *`` from a raw numeric address.  Useful when you have
   an address from a log or another tool::

      sdb> echo 0xffff9d0adbe2c000

``addr`` (alias ``address``)
   Resolves a symbol name **or** hex address to a drgn object, preserving
   type information::

      sdb> addr jiffies
      *(volatile unsigned long *)0xffffffff97205000 = 4901248625

   ``addr`` can take multiple arguments::

      sdb> addr jiffies slab_caches 0xffffdeadbeef

The difference: ``echo`` always produces ``void *``; ``addr`` produces a
typed pointer when given a symbol name.  In practice, ``addr`` is more
commonly used because you get type information for free.


Casting
-------

Explicit casting with the ``cast`` command:

.. code-block:: none

   sdb> echo 0xffff9d0adbe2c000 | cast spa_t *

``cast`` accepts any C type expression that drgn can resolve, including
typedefs, qualified types, and pointers to pointers.  It uses
``drgn.cast()`` under the hood.

As described in `Automatic type coercion`_, most casts happen implicitly
when piping ``void *`` objects into a command that declares an
``input_type``.
