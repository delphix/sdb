Developer notes
===============

This page covers the internals you need to know when writing sdb commands
or embedding sdb in your own tools.

.. contents:: On this page
   :local:
   :depth: 2


Writing a new command
---------------------

Every command is a Python class that inherits from ``sdb.Command`` (or one
of its subclasses).  The minimum requirements:

1. Set ``names`` to a non-empty list of strings.
2. Set ``load_on`` to control when the command is registered.
3. Implement ``_call`` (or the appropriate method for your base class).

Command names must follow C identifier rules: start with a letter or
underscore, followed by letters, digits, or underscores.  Names starting
with special characters like ``:``, ``%``, or ``/`` are rejected.

When a module containing your class is imported, ``Command.__init_subclass__``
automatically adds it to the global command set.  After ``register_commands()``
runs (which ``sdb.start()`` calls for you), the command is available in the
REPL with tab completion and ``help``.


Docstring conventions
^^^^^^^^^^^^^^^^^^^^^

The class docstring becomes the command's help text:

* **First line**: one-line summary shown in the ``help`` output header.
* **Remaining lines**: detailed description and examples.

Format your docstring like the built-in commands:

.. code-block:: python

   class MyCommand(sdb.Command):
       """
       One-line summary of what the command does

       DESCRIPTION
           Longer description of the command's behavior.

       EXAMPLES
           Show some typical invocations::

               sdb> my_command -v | head 5
       """

The ``DESCRIPTION`` and ``EXAMPLES`` headings are not mandatory but they
make the help text consistent with the built-in commands.


Adding arguments
^^^^^^^^^^^^^^^^

Override ``_init_parser`` to add argparse arguments:

.. code-block:: python

   @classmethod
   def _init_parser(cls, name: str) -> argparse.ArgumentParser:
       parser = super()._init_parser(name)
       parser.add_argument("-n", "--limit", type=int, default=10)
       return parser

Access them as ``self.args.limit`` in ``_call``.  If the user passes
invalid arguments, argparse raises a ``SystemExit`` which sdb catches and
converts to a ``CommandArgumentsError`` -- the REPL stays alive.


The ``@InputHandler`` decorator
-------------------------------

``InputHandler`` is used on methods of ``Locator`` subclasses to register
type-specific handlers.  When a Locator receives input, it dispatches to
the matching handler based on the input object's C type.

.. code-block:: python

   class SpaLocator(sdb.Locator, sdb.PrettyPrinter):
       names = ["spa"]
       output_type = "spa_t *"
       load_on = [sdb.Kernel()]

       def no_input(self):
           # Called when the command starts a pipeline
           ...

       @sdb.InputHandler("vdev_t *")
       def from_vdev(self, vdev):
           """Given a vdev, yield its parent spa."""
           yield vdev.vdev_spa

Dispatch order when a Locator receives an object:

1. Check ``@InputHandler``-decorated methods for a type match.
2. If the object already matches ``output_type``, pass it through.
3. Try the ``walk`` dispatch to iterate the object and cast each element
   to ``output_type``.
4. Raise ``CommandError`` if nothing matches.


Hybrid Locator / PrettyPrinter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A class can inherit from both ``Locator`` and ``PrettyPrinter``.  The
behavior adapts based on position in the pipeline:

* **First**: calls ``no_input()`` to locate objects, then pretty-prints.
* **Last**: receives input, locates matching objects, then pretty-prints.
* **Middle**: locates objects and passes them downstream (no printing).


The ``pre_cmd_hook`` mechanism
------------------------------

``sdb.start()`` accepts an optional ``pre_cmd_hook`` callable.  It is
invoked with no arguments immediately before each REPL command is evaluated.

.. code-block:: python

   sdb.start(prog, pre_cmd_hook=my_refresh_fn)

The hook is **not** called for meta-commands (``%session``,
``%load-commands``).

Use cases:

* **Cache invalidation**: bump a generation counter so stale pages are
  re-fetched (this is what GhostWire does).
* **Transport reconnection**: re-establish a connection if it dropped.
* **Telemetry**: count commands, measure latency.


Command registration internals
------------------------------

The registration flow:

1. When Python imports a module containing a ``Command`` subclass,
   ``__init_subclass__`` calls ``add_command(cls)`` which adds the class to
   the ``all_commands`` set.

2. ``register_commands()`` iterates ``all_commands`` and checks each class's
   ``load_on`` list against the current runtime (kernel or userland).  If
   appropriate, it calls ``register_command(name, cls)`` for each name in
   ``cls.names``.

3. ``register_command`` adds the name→class mapping to
   ``registered_commands`` and also registers Walkers and PrettyPrinters in
   their respective global lookup tables.

This means:

* Commands are discovered at import time (step 1).
* Commands are activated at registration time (step 2).
* ``load_external_commands()`` handles step 1 for files outside the sdb
  package.  You must call ``register_commands()`` afterward to activate them.
* ``sdb.start()`` calls both ``load_external_commands`` and
  ``register_commands`` for you.


Type canonicalization
---------------------

sdb normalises C types to handle typedefs, qualifiers, and pointer
variations.  The key helpers:

``type_canonicalize(type)``
   Strip all typedefs from a ``drgn.Type`` and return the underlying type.

``type_canonical_name(type)``
   Return the canonical name string after stripping typedefs.

``type_canonicalize_name(name)``
   Like ``type_canonical_name`` but accepts a name string.  Looks up the
   type via drgn first.

``type_equals(a, b)``
   Compare two types after canonicalization.

These are used internally by the pipeline's auto-coercion logic and by
Walkers and PrettyPrinters when matching input types.  If you write a
command that needs to compare types, prefer these over raw ``==`` on
``drgn.Type`` objects.


Error handling
--------------

sdb defines an error hierarchy rooted at ``sdb.Error``.  Commands should
raise these rather than printing error messages and returning:

``CommandError(command_name, message)``
   General runtime error.  The REPL prints it and returns to the prompt.

``SymbolNotFoundError(command_name, symbol)``
   A symbol name could not be resolved.

``CommandInvalidInputError(command_name, input_type, expected_type)``
   Type mismatch on input.

The REPL catches ``sdb.Error`` and prints ``err.text`` without a traceback.
Unexpected exceptions (anything not derived from ``sdb.Error``) trigger a
full traceback with a link to the issue tracker.


Testing commands
----------------

sdb uses pytest with a two-tier test strategy:

**Unit tests** (``tests/unit/``)
   Mock the drgn program and test command logic in isolation.  These run
   without any crash dump.

**Integration tests** (``tests/integration/``)
   Run commands against real crash dumps and compare output to reference
   files.  These require downloading test dumps first.

When contributing a new command, add at least a unit test that exercises the
core logic.  If the command depends on kernel data structures, add an
integration test with expected output.

Run the test suite:

.. code-block:: bash

   pip install -e ".[dev]"
   pytest -v tests/unit
