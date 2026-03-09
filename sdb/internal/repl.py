#
# Copyright 2019 Delphix
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import atexit
import json
import os
import readline
import shlex
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

import drgn
from sdb.error import Error, CommandArgumentsError
from sdb.loader import load_external_commands
from sdb.pipeline import invoke
from sdb.session import get_trace_manager

# Duplicated from sdb to avoid circular import (sdb -> sdb.internal.repl).
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_BAD_ARGS = 2


class REPL:
    """
    The class that provides the REPL for sdb. It is essentially a wrapper
    on top of readline and is the place where current and future
    enhancements in the interactivity of sdb should be placed (e.g.
    autocompletion, history, etc...).
    """

    @staticmethod
    def __make_completer(
            vocabulary: List[str]) -> Callable[[str, int], Optional[str]]:
        """
        Attribution:
        The following completer code came from Eli Berdensky's blog
        released under the public domain.
        """

        def custom_complete(text: str, state: int) -> Optional[str]:
            #
            # None is returned for the end of the completion session.
            #
            results: List[Optional[str]] = [
                x for x in vocabulary if x.startswith(text)
            ] + [None]

            #
            # A space is added to the completion since the Python readline
            # doesn't do this on its own. When a word is fully completed we
            # want to mimic the default readline library behavior of adding
            # a space after it.
            #
            result = results[state]
            if result is None:
                return None
            return result + " "

        return custom_complete

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            target: drgn.Program,
            vocabulary: List[str],
            prompt: str = "sdb> ",
            closing: str = "",
            pre_cmd_hook: Optional[Callable[[], None]] = None,
            json_mode: bool = False):
        self.prompt = prompt
        self.closing = closing
        self.vocabulary = vocabulary
        self.target = target
        self.histfile = ""
        self.pre_cmd_hook = pre_cmd_hook
        self.json_mode = json_mode
        readline.set_completer(REPL.__make_completer(vocabulary))
        readline.parse_and_bind("tab: complete")

    def enable_history(self, history_file: str) -> None:
        self.histfile = os.path.expanduser(history_file)
        try:
            readline.read_history_file(self.histfile)
        except FileNotFoundError:
            pass
        except PermissionError:
            self.histfile = ""
            print(
                f"Warning: You don't have permissions to read {history_file} and\n"
                "         the command history of this session won't be saved.\n"
                "         Either change this file's permissions, recreate it,\n"
                "         or use an alternate path with the SDB_HISTORY_FILE\n"
                "         environment variable.")
            return
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, self.histfile)

    def refresh_vocabulary(self) -> None:
        """Rebuild the tab-completion vocabulary from registered commands."""
        from sdb.command import get_registered_commands
        self.vocabulary = list(get_registered_commands().keys())
        readline.set_completer(REPL.__make_completer(self.vocabulary))

    def _handle_load_commands(self, args: List[str]) -> int:
        """Handle %load-commands <path> meta-command."""
        if not args:
            print("Usage: %load-commands <file-or-directory>")
            return EXIT_BAD_ARGS

        from sdb.command import register_commands
        path = args[0]
        try:
            new_names = load_external_commands(path)
        except (FileNotFoundError, ImportError, ValueError) as e:
            print(f"Error loading commands: {e}")
            return EXIT_ERROR

        register_commands()
        self.refresh_vocabulary()

        if new_names:
            print(f"Loaded {len(new_names)} command(s): {', '.join(new_names)}")
        else:
            print(f"No new commands found in {path}")
        return EXIT_SUCCESS

    def _parse_session_cmd(self, input_: str) -> Tuple[str, List[str]]:
        """Parse session command input into subcmd and args."""
        parts = shlex.split(input_)
        if not parts or parts[0] != 'session':
            return ('', parts)
        if len(parts) < 2:
            return ('', parts)
        return (parts[1], parts[2:])

    def _handle_session_record(self, args: List[str]) -> int:
        """Handle %session record command."""
        if not args:
            print("Usage: %session record <file>")
            print("       Output will be saved as <file>.vmcore.recorded")
            return EXIT_BAD_ARGS
        output_path = args[0]
        trace_mgr = get_trace_manager()
        trace_mgr.start_recording(self.target, output_path)
        print(f"Recording started. Output: {trace_mgr.output_path}")
        return EXIT_SUCCESS

    def _handle_session_stop(self) -> int:
        """Handle %session stop command."""
        trace_mgr = get_trace_manager()
        saved_path = trace_mgr.stop_recording(self.target)
        status = trace_mgr.get_status()
        print("Recording stopped.")
        print(f"Saved to: {saved_path}")
        print(f"  Memory segments: {status['memory_segments']}")
        print(f"  Memory size: {status['memory_size']} bytes")
        return EXIT_SUCCESS

    def _handle_session_status(self) -> int:
        """Handle %session status command."""
        trace_mgr = get_trace_manager()
        status = trace_mgr.get_status()
        if status['is_recording']:
            print(f"Recording to: {status['output_path']}")
            print(f"  Format: {status['output_format']}")
            if status['output_format'] == 'kdump':
                print(
                    f"  Compression: {status['compression']} (level {status['compression_level']})"
                )
            print(f"  Memory segments: {status['memory_segments']}")
            print(f"  Memory size: {status['memory_size']} bytes")
        elif status['is_replay']:
            print("Replay mode active")
        else:
            print("No recording or replay in progress")
            print(f"Default format: {status['output_format']}")
            if status['output_format'] == 'kdump':
                compression = status['compression']
                level = status['compression_level']
                print(f"Default compression: {compression} (level {level})")
        return EXIT_SUCCESS

    def _handle_session_snapshot(self, args: List[str]) -> int:
        """Handle %session snapshot command."""
        if not args:
            print("Usage: %session snapshot <variable> [--depth N]")
            return EXIT_BAD_ARGS
        var_name = args[0]
        depth = 1
        if len(args) >= 3 and args[1] == '--depth':
            try:
                depth = int(args[2])
            except ValueError:
                print(f"Invalid depth: {args[2]}")
                return EXIT_BAD_ARGS

        trace_mgr = get_trace_manager()
        if not trace_mgr.is_recording:
            print(
                "Error: No recording in progress. Use '%session record <file>' first."
            )
            return EXIT_ERROR

        # Force read the variable to capture it
        try:
            import sdb.target as sdb_target
            obj = sdb_target.get_object(var_name)
            # Use capture_object for proper tracing
            trace_mgr.capture_object(obj, depth)
            status = trace_mgr.get_status()
            print(f"Snapshot captured: {var_name}")
            print(f"  Memory segments: {status['memory_segments']}")
            print(f"  Memory size: {status['memory_size']} bytes")
        except (drgn.FaultError, ValueError, TypeError, LookupError) as e:
            print(f"Failed to snapshot {var_name}: {e}")
            return EXIT_ERROR
        return EXIT_SUCCESS

    def _handle_session_load(self, args: List[str]) -> int:
        """Handle %session load command."""
        if not args:
            print("Usage: %session load <file.vmcore.recorded>")
            return EXIT_BAD_ARGS
        # Note: Loading is primarily done via CLI --replay
        print("Note: Use 'sdb --replay <file>' to load a recorded session")
        print("      The %session load command is for advanced use cases")
        return EXIT_SUCCESS

    def _handle_session_record_memory(self, args: List[str]) -> int:
        """Handle %session record-memory command."""
        trace_mgr = get_trace_manager()
        if not trace_mgr.is_recording:
            print("Error: Not recording. Use '%session record <file>' first.")
            return EXIT_ERROR

        # Parse arguments: <address> <size> [--physical]
        physical = '--physical' in args
        # Remove --physical from args for parsing address and size
        args = [a for a in args if a != '--physical']

        if len(args) < 2:
            print("Usage: %session record-memory <address> <size> [--physical]")
            return EXIT_BAD_ARGS

        try:
            # Parse address (supports hex with 0x prefix)
            address = int(args[0], 0)
            size = int(args[1], 0)
        except ValueError as e:
            print(f"Invalid address or size: {e}")
            return EXIT_BAD_ARGS

        if size <= 0:
            print("Error: size must be positive")
            return EXIT_BAD_ARGS

        try:
            trace_mgr.trace_read(address, size, physical)
            phys_str = " (physical)" if physical else ""
            print(f"Recorded {size} bytes at {hex(address)}{phys_str}")
            return EXIT_SUCCESS
        except drgn.FaultError as e:
            print(f"Failed to read memory at {hex(address)}: {e}")
            return EXIT_ERROR

    def _handle_session_config(self, args: List[str]) -> int:  # pylint: disable=too-many-return-statements,too-many-branches
        """Handle %session config command."""
        trace_mgr = get_trace_manager()

        if not args:
            # Show current config
            print("Current session configuration:")
            print(f"  Format: {trace_mgr.output_format}")
            if trace_mgr.output_format == 'kdump':
                print(f"  Compression: {trace_mgr.compression}")
                print(f"  Compression level: {trace_mgr.compression_level}")
            else:
                print(
                    "  Compression: n/a (ELF format does not use compression)")
            print()
            print("Usage: %session config <option> <value>")
            print("Options:")
            print("  format <elf|kdump>        - Set output format")
            print("  compression <type>        - Set compression (kdump only)")
            print(
                "                              Types: none, zlib, lzo, snappy, zstd"
            )
            print(
                "  compression-level <1-9>   - Set compression level (kdump only)"
            )
            return EXIT_SUCCESS

        option = args[0].lower()

        if option == 'format':
            if len(args) < 2:
                print("Usage: %session config format <elf|kdump>")
                return EXIT_BAD_ARGS
            try:
                trace_mgr.set_output_format(args[1])
                print(f"Output format set to: {trace_mgr.output_format}")
                if trace_mgr.output_format == 'kdump':
                    print(f"  Compression: {trace_mgr.compression}")
                return EXIT_SUCCESS
            except ValueError as e:
                print(f"Error: {e}")
                return EXIT_ERROR

        if option == 'compression':
            if len(args) < 2:
                print(
                    "Usage: %session config compression <none|zlib|lzo|snappy|zstd>"
                )
                return EXIT_BAD_ARGS
            try:
                trace_mgr.set_compression(args[1])
                print(f"Compression set to: {trace_mgr.compression}")
                if trace_mgr.output_format != 'kdump':
                    print("Note: Compression only applies to kdump format")
                return EXIT_SUCCESS
            except ValueError as e:
                print(f"Error: {e}")
                return EXIT_ERROR

        if option in ('compression-level', 'level'):
            if len(args) < 2:
                print("Usage: %session config compression-level <1-9>")
                return EXIT_BAD_ARGS
            try:
                level = int(args[1])
                trace_mgr.set_compression(trace_mgr.compression, level)
                print(
                    f"Compression level set to: {trace_mgr.compression_level}")
                return EXIT_SUCCESS
            except ValueError as e:
                print(f"Error: {e}")
                return EXIT_ERROR

        print(f"Unknown config option: {option}")
        print("Options: format, compression, compression-level")
        return EXIT_ERROR

    # pylint: disable=too-many-return-statements,too-many-branches
    def eval_session_cmd(self, input_: str) -> int:
        """
        Evaluates a session command (commands starting with %).

        Session commands control recording and replay functionality:
        - %session record <file> - Start recording (saves as .vmcore.recorded)
        - %session stop - Stop recording and save
        - %session status - Show recording status
        - %session config [option] [value] - Configure format/compression
        - %session snapshot <var> [--depth N] - Capture object graph
        - %session record-memory <addr> <size> - Capture memory region
        - %session load <file> - Load a recorded session
        - %load-commands <path> - Load external sdb commands

        Returns:
            0 for success
            1 for error
            2 for incorrect arguments
        """
        try:
            # Parse the session command
            parts = shlex.split(input_)
            if not parts:
                print("Usage: %session <command> [args]")
                print(
                    "Commands: record, stop, status, config, snapshot, record-memory, load"
                )
                return EXIT_BAD_ARGS

            if parts[0] == 'load-commands':
                return self._handle_load_commands(parts[1:])

            if parts[0] != 'session':
                print(f"Unknown meta-command: %{parts[0]}")
                print("Available meta-commands: %session, %load-commands")
                return EXIT_ERROR

            if len(parts) < 2:
                print("Usage: %session <command> [args]")
                print(
                    "Commands: record, stop, status, config, snapshot, record-memory, load"
                )
                return EXIT_BAD_ARGS

            subcmd = parts[1]
            args = parts[2:]

            if subcmd == 'record':
                return self._handle_session_record(args)
            if subcmd == 'stop':
                return self._handle_session_stop()
            if subcmd == 'status':
                return self._handle_session_status()
            if subcmd == 'config':
                return self._handle_session_config(args)
            if subcmd == 'snapshot':
                return self._handle_session_snapshot(args)
            if subcmd == 'record-memory':
                return self._handle_session_record_memory(args)
            if subcmd == 'load':
                return self._handle_session_load(args)

            print(f"Unknown session command: {subcmd}")
            print(
                "Commands: record, stop, status, config, snapshot, record-memory, load"
            )
            return EXIT_ERROR

        except RuntimeError as e:
            print(f"Session error: {e}")
            return EXIT_ERROR
        except (ValueError, TypeError, OSError) as e:
            print(f"Session command failed: {e}")
            return EXIT_ERROR

    @staticmethod
    # pylint: disable=import-outside-toplevel
    def _serialize_json(objs: List[drgn.Object]) -> List[Dict[str, Any]]:
        """Serialize pipeline output objects to JSON.

        If the terminal command is a PrettyPrinter that overrides
        ``to_json_aggregate()``, delegate to it so it can perform
        cross-object transformations (grouping, sorting, etc.).
        Otherwise, fall back to per-object generic serialization.
        """
        from sdb.command import PrettyPrinter, get_active_json_printer
        active = get_active_json_printer()
        if active is not None:
            # Check if the subclass actually overrode to_json_aggregate
            if type(active
                   ).to_json_aggregate is not PrettyPrinter.to_json_aggregate:
                return active.to_json_aggregate(objs)
            # Subclass has per-object to_json but not aggregate — use it
            if type(active).to_json is not PrettyPrinter.to_json:
                results: List[Dict[str, Any]] = []
                for obj in objs:
                    entry = active.to_json(obj)
                    if entry:
                        results.append(entry)
                    else:
                        results.append(REPL._obj_to_json(obj))
                return results
        return [REPL._obj_to_json(obj) for obj in objs]

    @staticmethod
    # pylint: disable=broad-exception-caught,too-many-branches,import-outside-toplevel
    def _obj_to_json(obj: drgn.Object) -> Dict[str, Any]:
        """Convert a drgn.Object to a JSON-serializable dict.

        If the object's type has a registered PrettyPrinter with a custom
        to_json() override, that method is used. Otherwise, the generic
        drgn.Object serialization is used.
        """
        from sdb.command import PrettyPrinter
        from sdb.target import type_canonical_name

        # Check if there's a PrettyPrinter with a custom to_json() for this type.
        try:
            type_name = type_canonical_name(obj.type_)
            if type_name in PrettyPrinter.all_printers:
                printer_cls = PrettyPrinter.all_printers[type_name]
                # Only use it if the subclass actually overrode to_json()
                if printer_cls.to_json is not PrettyPrinter.to_json:
                    custom = printer_cls().to_json(obj)
                    if custom:
                        return custom
        except Exception:
            pass

        result: Dict[str, Any] = {}
        result["type"] = obj.type_.type_name()

        # Try to get the address
        if obj.address_ is not None:
            result["address"] = hex(obj.address_)

        # Try to get a scalar value
        try:
            val = obj.value_()
            if isinstance(val, int):
                result["value"] = val
            elif isinstance(val, float):
                result["value"] = val
            elif isinstance(val, bytes):
                # Try to decode as string first (char arrays)
                try:
                    result["value"] = val.rstrip(b'\x00').decode(
                        'utf-8', errors='replace')
                except Exception:
                    result["value"] = val.hex()
            elif isinstance(val, dict):
                # struct/union — keys are member names
                json_members: Dict[str, Any] = {}
                for k, v in val.items():
                    if isinstance(v, int):
                        json_members[k] = v
                    else:
                        json_members[k] = str(v)
                result["value"] = json_members
            else:
                result["value"] = str(val)
        except Exception:
            # Fall back to format_() for complex types
            try:
                result["value"] = obj.format_(dereference=False)
            except Exception:
                result["value"] = str(obj)

        return result

    # pylint: disable=too-many-return-statements,too-many-statements,too-many-branches
    def eval_cmd(self, input_: str) -> int:
        """
        Evaluates the SDB command/pipeline passed as input_
        and prints the result.

        Returns:
            ``sdb.EXIT_SUCCESS`` (0) for success,
            ``sdb.EXIT_ERROR`` (1) for a command error,
            ``sdb.EXIT_BAD_ARGS`` (2) for incorrect arguments.
        """
        # Check for session/meta commands (starting with %)
        if input_.startswith('%'):
            return self.eval_session_cmd(input_[1:])

        if self.pre_cmd_hook is not None:
            self.pre_cmd_hook()

        # Check if recording is active
        trace_mgr = get_trace_manager()
        is_tracing = trace_mgr.is_recording

        # Activate JSON mode globally so command _call() methods can
        # bypass pretty_print() and yield objects for serialization.
        if self.json_mode:
            from sdb.command import set_json_mode  # pylint: disable=import-outside-toplevel
            set_json_mode(True)

        # pylint: disable=broad-except
        json_objs: Optional[List[drgn.Object]] = ([]
                                                  if self.json_mode else None)
        try:
            try:
                for obj in invoke([], input_):
                    # If recording, capture the object's memory
                    if is_tracing and hasattr(obj, 'address_of_'):
                        try:
                            trace_mgr.capture_object(obj, depth=0)
                        except Exception:
                            pass  # Don't let tracing errors break commands

                    if self.json_mode and json_objs is not None:
                        json_objs.append(obj)
                    else:
                        try:
                            print(obj.format_(dereference=False))
                        except AttributeError:
                            print(obj)
            except CommandArgumentsError as err:
                #
                # We skip printing anything for this specific error
                # as argparse should have already printed a helpful
                # message to the REPL for us.
                #
                if self.json_mode:
                    json.dump({"error": str(err)}, sys.stdout)
                    print()
                return EXIT_BAD_ARGS
            except Error as err:
                if self.json_mode:
                    json.dump({"error": err.text}, sys.stdout)
                    print()
                else:
                    print(err.text)
                return EXIT_ERROR
            except KeyboardInterrupt:
                #
                # Interrupting commands half way through their execution
                # (e.g. with Ctrl+c) should be allowed. Note that we
                # print a new line for better formatting of the next
                # prompt.
                #
                print()
                return EXIT_ERROR
            except BrokenPipeError:
                #
                # If a shell process (invoked by !) exits before reading all
                # of its input, that's OK.
                #
                return EXIT_ERROR
            except Exception:
                #
                # Ideally it would be great if all commands had no issues and
                # would take care of all their possible edge case. That is
                # something that we should strive for and ask in code reviews
                # when introducing commands. Looking into the long-term though
                # if SDB commands/modules are to be decoupled from the SDB repo,
                # it can be harder to have control over the quality of the
                # commands imported by SDB during the runtime.
                #
                # Catching all exceptions from the REPL may be a bit ugly as a
                # programming practice in general. That said in this case, not
                # catching these errors leads to the worst outcome in terms of
                # user-experience that you can get from SDB - getting dropped
                # out of SDB with a non-friendly error message. Furthermore,
                # given that there is no state maintained in the REPL between
                # commands, attempting to recover after a command error is not
                # that bad and most probably won't lead to any problems in
                # future commands issued within the same session.
                #
                print(
                    "sdb encountered an internal error due to a bug. Here's the"
                )
                print("information you need to file the bug:")
                print(
                    "----------------------------------------------------------"
                )
                print("Target Info:")
                print(f"\t{self.target.flags}")
                print(f"\t{self.target.platform}")
                print()
                traceback.print_exc()
                print(
                    "----------------------------------------------------------"
                )
                print("Link: https://github.com/delphix/sdb/issues/new")
                return EXIT_ERROR

            if self.json_mode and json_objs is not None:
                json_results = self._serialize_json(json_objs)
                json.dump(json_results, sys.stdout, indent=2)
                print()
            return EXIT_SUCCESS
        finally:
            if self.json_mode:
                from sdb.command import set_json_mode  # pylint: disable=import-outside-toplevel
                set_json_mode(False)

    def start_session(self) -> None:
        """
        Starts a REPL session.
        """
        while True:
            try:
                line = input(self.prompt).strip()
            except KeyboardInterrupt:
                #
                # Pressing Ctrl+C while in the middle of writing
                # a command or before even typing anything should
                # bring back a new prompt. The user should use
                # Ctrl+d if they need to exit without typing a
                # command.
                #
                # We clear out `line` and print a new line so we
                # don't display multiple prompts within the same
                # line.
                #
                line = ""
                print()
            except (EOFError, SystemExit):
                print(self.closing)
                break

            if not line:
                continue
            _ = self.eval_cmd(line)
