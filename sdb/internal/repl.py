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
import os
import readline
import shlex
import traceback
from typing import Callable, List, Optional, Tuple

import drgn
from sdb.error import Error, CommandArgumentsError
from sdb.pipeline import invoke
from sdb.session import get_trace_manager


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

    def __init__(self,
                 target: drgn.Program,
                 vocabulary: List[str],
                 prompt: str = "sdb> ",
                 closing: str = ""):
        self.prompt = prompt
        self.closing = closing
        self.vocabulary = vocabulary
        self.target = target
        self.histfile = ""
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
            print("Usage: %session record <file.sdb>")
            return 2
        output_path = args[0]
        trace_mgr = get_trace_manager()
        trace_mgr.start_recording(self.target, output_path)
        print(f"Recording started. Output will be saved to: {output_path}")
        return 0

    def _handle_session_stop(self) -> int:
        """Handle %session stop command."""
        trace_mgr = get_trace_manager()
        saved_path = trace_mgr.stop_recording(self.target)
        status = trace_mgr.get_status()
        print("Recording stopped.")
        print(f"Saved to: {saved_path}")
        print(f"  Memory segments: {status['memory_segments']}")
        print(f"  Memory size: {status['memory_size']} bytes")
        print(f"  Objects: {status['objects_count']}")
        print(f"  Symbols: {status['symbols_count']}")
        return 0

    def _handle_session_status(self) -> int:
        """Handle %session status command."""
        trace_mgr = get_trace_manager()
        status = trace_mgr.get_status()
        if status['is_recording']:
            print(f"Recording to: {status['output_path']}")
            print(f"  Memory segments: {status['memory_segments']}")
            print(f"  Memory size: {status['memory_size']} bytes")
            print(f"  Objects: {status['objects_count']}")
        elif status['is_replay']:
            print("Replay mode active")
            print(f"  Memory segments: {status['memory_segments']}")
            print(f"  Memory size: {status['memory_size']} bytes")
        else:
            print("No recording or replay in progress")
        return 0

    def _handle_session_snapshot(self, args: List[str]) -> int:
        """Handle %session snapshot command."""
        if not args:
            print("Usage: %session snapshot <variable> [--depth N]")
            return 2
        var_name = args[0]
        depth = 1
        if len(args) >= 3 and args[1] == '--depth':
            try:
                depth = int(args[2])
            except ValueError:
                print(f"Invalid depth: {args[2]}")
                return 2

        trace_mgr = get_trace_manager()
        if not trace_mgr.is_recording:
            print(
                "Error: No recording in progress. Use '%session record <file>' first."
            )
            return 1

        # Force read the variable to capture it
        try:
            import sdb.target as sdb_target
            obj = sdb_target.get_object(var_name)
            # Use capture_object for proper tracing
            trace_mgr.capture_object(obj, depth)
            # Also record the named object
            trace_mgr.record_object(var_name, int(obj.address_of_()),
                                    str(obj.type_))
            status = trace_mgr.get_status()
            print(f"Snapshot captured: {var_name}")
            print(f"  Memory segments: {status['memory_segments']}")
            print(f"  Memory size: {status['memory_size']} bytes")
        except (drgn.FaultError, ValueError, TypeError, LookupError) as e:
            print(f"Failed to snapshot {var_name}: {e}")
            return 1
        return 0

    def _handle_session_load(self, args: List[str]) -> int:
        """Handle %session load command."""
        if not args:
            print("Usage: %session load <file.sdb>")
            return 2
        # Note: Loading is primarily done via CLI --replay
        # This command is for switching to a loaded session
        print("Note: Use 'sdb --replay <file.sdb>' to load a recorded session")
        print("      The %session load command is for advanced use cases")
        return 0

    def _handle_session_capture_stacks(self, args: List[str]) -> int:
        """Handle %session capture-stacks command."""
        trace_mgr = get_trace_manager()
        if not trace_mgr.is_recording:
            print("Error: Not recording. Use '%session record <file>' first.")
            return 1

        include_locals = '--no-locals' not in args
        count = trace_mgr.capture_all_stacks(self.target, include_locals)

        status = trace_mgr.get_status()
        print(f"Captured {count} thread stacks")
        print(f"  Memory segments: {status['memory_segments']}")
        print(f"  Memory size: {status['memory_size']} bytes")
        print(f"  Symbols: {status['symbols_count']}")
        print(f"  Threads: {status['threads_count']}")
        if not include_locals:
            print(
                "  (stack memory not captured - locals unavailable during replay)"
            )
        return 0

    def _handle_session_record_memory(self, args: List[str]) -> int:
        """Handle %session record-memory command."""
        trace_mgr = get_trace_manager()
        if not trace_mgr.is_recording:
            print("Error: Not recording. Use '%session record <file>' first.")
            return 1

        # Parse arguments: <address> <size> [--physical]
        physical = '--physical' in args
        # Remove --physical from args for parsing address and size
        args = [a for a in args if a != '--physical']

        if len(args) < 2:
            print("Usage: %session record-memory <address> <size> [--physical]")
            return 2

        try:
            # Parse address (supports hex with 0x prefix)
            address = int(args[0], 0)
            size = int(args[1], 0)
        except ValueError as e:
            print(f"Invalid address or size: {e}")
            return 2

        if size <= 0:
            print("Error: size must be positive")
            return 2

        try:
            trace_mgr.trace_read(address, size, physical)
            phys_str = " (physical)" if physical else ""
            print(f"Recorded {size} bytes at {hex(address)}{phys_str}")
            return 0
        except drgn.FaultError as e:
            print(f"Failed to read memory at {hex(address)}: {e}")
            return 1

    # pylint: disable=too-many-return-statements
    def eval_session_cmd(self, input_: str) -> int:
        """
        Evaluates a session command (commands starting with %).

        Session commands control recording and replay functionality:
        - %session record <file.sdb> - Start recording
        - %session stop - Stop recording and save
        - %session status - Show recording status
        - %session snapshot <var> [--depth N] - Capture object graph
        - %session load <file.sdb> - Load a recorded session

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
                print("Commands: record, stop, status, snapshot, load")
                return 2

            if parts[0] != 'session':
                print(f"Unknown meta-command: %{parts[0]}")
                print("Available meta-commands: %session")
                return 1

            if len(parts) < 2:
                print("Usage: %session <command> [args]")
                print("Commands: record, stop, status, snapshot, "
                      "capture-stacks, record-memory, load")
                return 2

            subcmd = parts[1]
            args = parts[2:]

            if subcmd == 'record':
                return self._handle_session_record(args)
            if subcmd == 'stop':
                return self._handle_session_stop()
            if subcmd == 'status':
                return self._handle_session_status()
            if subcmd == 'snapshot':
                return self._handle_session_snapshot(args)
            if subcmd == 'capture-stacks':
                return self._handle_session_capture_stacks(args)
            if subcmd == 'record-memory':
                return self._handle_session_record_memory(args)
            if subcmd == 'load':
                return self._handle_session_load(args)

            print(f"Unknown session command: {subcmd}")
            print("Commands: record, stop, status, snapshot, "
                  "capture-stacks, record-memory, load")
            return 1

        except RuntimeError as e:
            print(f"Session error: {e}")
            return 1
        except (ValueError, TypeError, OSError) as e:
            print(f"Session command failed: {e}")
            return 1

    # pylint: disable=too-many-return-statements
    def eval_cmd(self, input_: str) -> int:
        """
        Evaluates the SDB command/pipeline passed as input_
        and prints the result.

        Returns:
            0 for success
            1 for error
            2 for incorrect arguments passed
        """
        # Check for session/meta commands (starting with %)
        if input_.startswith('%'):
            return self.eval_session_cmd(input_[1:])

        # Check if recording is active
        trace_mgr = get_trace_manager()
        is_tracing = trace_mgr.is_recording

        # pylint: disable=broad-except
        try:
            for obj in invoke([], input_):
                # If recording, capture the object's memory
                if is_tracing and hasattr(obj, 'address_of_'):
                    try:
                        trace_mgr.capture_object(obj, depth=0)
                    except Exception:
                        pass  # Don't let tracing errors break commands

                try:
                    print(obj.format_(dereference=False))
                except AttributeError:
                    print(obj)
        except CommandArgumentsError:
            #
            # We skip printing anything for this specific error
            # as argparse should have already printed a helpful
            # message to the REPL for us.
            #
            return 2
        except Error as err:
            print(err.text)
            return 1
        except KeyboardInterrupt:
            #
            # Interrupting commands half way through their execution
            # (e.g. with Ctrl+c) should be allowed. Note that we
            # print a new line for better formatting of the next
            # prompt.
            #
            print()
            return 1
        except BrokenPipeError:
            #
            # If a shell process (invoked by !) exits before reading all
            # of its input, that's OK.
            #
            return 1
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
            print("sdb encountered an internal error due to a bug. Here's the")
            print("information you need to file the bug:")
            print("----------------------------------------------------------")
            print("Target Info:")
            print(f"\t{self.target.flags}")
            print(f"\t{self.target.platform}")
            print()
            traceback.print_exc()
            print("----------------------------------------------------------")
            print("Link: https://github.com/delphix/sdb/issues/new")
            return 1
        return 0

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
