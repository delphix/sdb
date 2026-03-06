Public API reference
====================

This page documents the public Python API exported by the ``sdb`` package.
Everything listed here is part of ``sdb.__all__`` and is considered stable.

.. contents:: On this page
   :local:
   :depth: 2


Entry point
-----------

.. function:: sdb.start(prog, command_paths=None, prompt="sdb> ", pre_cmd_hook=None, eval_cmd=None, history_file="~/.sdb_history")

   High-level entry point for using sdb as a library.

   Accepts a pre-configured :class:`drgn.Program` and starts the sdb REPL
   (or evaluates a single command if *eval_cmd* is given).

   :param prog: A fully initialised ``drgn.Program``.
   :param command_paths: Optional list of filesystem paths (files or
       directories) from which to load additional sdb commands.
   :param prompt: REPL prompt string, or an object whose ``__str__`` is
       called each time the prompt is displayed.
   :param pre_cmd_hook: Optional callable (no arguments) invoked before
       every command evaluation.
   :param eval_cmd: If provided, evaluate this single command string and
       return instead of starting the interactive REPL.
   :param history_file: Path for readline history persistence.

   Example:

   .. code-block:: python

      import drgn, sdb

      prog = drgn.Program()
      prog.set_kernel()
      prog.load_default_debug_info()

      sdb.start(prog, prompt="mydb> ")


Pipeline execution
------------------

.. function:: sdb.invoke(first_input, line)

   Parse and execute an sdb pipeline string.

   :param first_input: An iterable of ``drgn.Object`` to feed as initial
       input (pass ``[]`` to start from scratch).
   :param line: The pipeline string, e.g. ``"stacks -t D | count"``.
   :returns: A generator yielding ``drgn.Object`` results.

   Example:

   .. code-block:: python

      for obj in sdb.invoke([], "spa | member spa_name"):
          print(obj.string_().decode())

.. function:: sdb.execute_pipeline(first_input, pipeline)

   Execute a pre-built list of ``Command`` objects.

   :param first_input: Iterable of ``drgn.Object``.
   :param pipeline: A list of instantiated ``Command`` objects.
   :returns: Generator of ``drgn.Object``.

.. function:: sdb.get_first_type(objs)

   Peek at the type of the first object in an iterable without consuming it.

   :param objs: An iterable of ``drgn.Object``.
   :returns: A tuple ``(drgn.Type, iterable)`` where the iterable contains
       the same objects (including the first one).

   Example:

   .. code-block:: python

      first_type, objs = sdb.get_first_type(objs)


External command loading
------------------------

.. function:: sdb.load_external_commands(path)

   Import sdb commands from a ``.py`` file or a directory of them.

   :param path: Filesystem path.  If a directory, all ``.py`` files are
       imported recursively (files starting with ``__`` are skipped).
   :returns: A list of command name strings that were newly discovered.
   :raises FileNotFoundError: If *path* does not exist.
   :raises ImportError: If a module fails to load.

   After loading, call :func:`sdb.register_commands` to make the new
   commands available in the REPL.


Command registration
--------------------

.. function:: sdb.register_commands()

   Register all known command classes that are appropriate for the current
   runtime (kernel vs. userland).  This is called automatically by
   :func:`sdb.start`; call it manually only when setting up sdb without
   ``start()``.

.. function:: sdb.get_registered_commands()

   Return a dict mapping command name strings to ``Command`` subclasses.


Target helpers
--------------

These functions access the ``drgn.Program`` and its state.  They are
available after ``sdb.start()`` has been called or after manually calling
``sdb.target.set_prog()``.

.. function:: sdb.get_prog()

   Return the current ``drgn.Program``.

.. function:: sdb.get_object(name)

   Look up a global variable or symbol by name and return it as a
   ``drgn.Object``.

.. function:: sdb.create_object(type, value)

   Create a ``drgn.Object`` of the given type with the given value.

   :param type: A type string (e.g. ``"void *"``, ``"int"``).
   :param value: An integer value.

.. function:: sdb.get_type(name)

   Look up a C type by name and return a ``drgn.Type``.

.. function:: sdb.get_symbol(obj)

   Return the ``drgn.Symbol`` for an object or address.

.. function:: sdb.get_pointer_type(type)

   Given a ``drgn.Type``, return the corresponding pointer type.

.. function:: sdb.is_null(obj)

   Return ``True`` if *obj* is a null pointer.

.. function:: sdb.get_target_flags()

   Return the ``drgn.ProgramFlags`` for the current program.


Thread and frame state
^^^^^^^^^^^^^^^^^^^^^^

.. function:: sdb.set_thread(thread)

   Set the current thread context.

.. function:: sdb.get_thread()

   Return the current thread object.

.. function:: sdb.set_frame(frame)

   Set the current stack frame index (``-1`` for the topmost frame).

.. function:: sdb.get_frame()

   Return the current stack frame index.


Type utilities
^^^^^^^^^^^^^^

.. function:: sdb.type_canonical_name(type)

   Return the canonical name for a ``drgn.Type`` (resolves typedefs).

.. function:: sdb.type_canonicalize(type)

   Resolve all typedefs and return the underlying ``drgn.Type``.

.. function:: sdb.type_canonicalize_name(name)

   Like ``type_canonical_name`` but accepts a type name string.

.. function:: sdb.type_canonicalize_size(type)

   Return the size of a type after resolving typedefs.

.. function:: sdb.type_equals(a, b)

   Return ``True`` if two ``drgn.Type`` objects refer to the same type
   (after canonicalization).


Command base classes
--------------------

.. class:: sdb.Command

   Base class for all sdb commands.  See :doc:`developer-notes` for how
   to subclass it.

.. class:: sdb.SingleInputCommand

   Processes each input object independently; a ``FaultError`` on one
   object does not abort the pipeline.

.. class:: sdb.Walker

   Iterates over a container data structure.  Implement ``walk(self, obj)``.

.. class:: sdb.PrettyPrinter

   Human-readable formatter.  Implement ``pretty_print(self, objs)``.

.. class:: sdb.Locator

   Finds objects of a given type.  Implement ``no_input(self)`` and
   optionally ``@InputHandler``-decorated methods.

.. class:: sdb.InputHandler(typename)

   Decorator for methods on Locator subclasses.  Registers the method as
   the handler for input objects of the given C type.

.. class:: sdb.Address

   Built-in command that resolves symbols and hex addresses.

.. class:: sdb.Cast

   Built-in command that casts objects to a specified type.

.. class:: sdb.Walk

   Built-in dispatch command that selects the appropriate Walker.


Runtime markers
---------------

.. class:: sdb.All

   Load the command for all target types.

.. class:: sdb.Kernel

   Load the command only for kernel targets.

.. class:: sdb.Userland

   Load the command only for userland targets.

.. class:: sdb.Module(name)

   Load for a specific kernel module (currently equivalent to ``Kernel``).

.. class:: sdb.Library(name)

   Load for a specific shared library (currently equivalent to ``Userland``).


Error hierarchy
---------------

All sdb-specific exceptions inherit from ``sdb.Error``.

.. class:: sdb.Error

   Base exception.

.. class:: sdb.CommandError

   A command encountered a runtime error (e.g. type mismatch, invalid
   memory).

.. class:: sdb.CommandNotFoundError

   The user typed a command name that is not registered.

.. class:: sdb.CommandInvalidInputError

   A command received input of an unexpected type.

.. class:: sdb.SymbolNotFoundError

   A symbol name could not be resolved.

.. class:: sdb.CommandArgumentsError

   The arguments passed to a command were invalid (raised by argparse).

.. class:: sdb.CommandEvalSyntaxError

   A syntax error in a filter expression.

.. class:: sdb.ParserError

   A parse error in the pipeline syntax.
