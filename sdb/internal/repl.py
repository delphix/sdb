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

# pylint: disable=missing-docstring

import atexit
import os
import readline
import traceback

from sdb.error import Error, CommandArgumentsError
from sdb.pipeline import invoke


class REPL:
    """
    The class that provides the REPL for sdb. It is essentially a wrapper
    on top of readline and is the place where current and future
    enhancements in the interactivity of sdb should be placed (e.g.
    autocompletion, history, etc...).
    """

    @staticmethod
    def __make_completer(vocabulary):
        """
        Attribution:
        The following completer code came from Eli Berdensky's blog
        released under the public domain.
        """

        def custom_complete(text, state):
            # None is returned for the end of the completion session.
            results = [x for x in vocabulary if x.startswith(text)] + [None]
            # A space is added to the completion since the Python readline
            # doesn't do this on its own. When a word is fully completed we
            # want to mimic the default readline library behavior of adding
            # a space after it.
            return results[state] + " "

        return custom_complete

    def __init__(self, target, vocabulary, prompt="sdb> ", closing=""):
        self.prompt = prompt
        self.closing = closing
        self.vocabulary = vocabulary
        self.target = target
        self.histfile = ""
        readline.set_completer(REPL.__make_completer(vocabulary))

    def enable_history(self, history_file='~/.sdb_history'):
        self.histfile = os.path.expanduser(history_file)
        try:
            readline.read_history_file(self.histfile)
        except FileNotFoundError:
            pass
        readline.parse_and_bind("tab: complete")
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, self.histfile)

    def eval_cmd(self, input_: str) -> int:
        """
        Evaluates the SDB command/pipeline passed as input_
        and prints the result.

        Returns:
            0 for success
            1 for error
            2 for incorrect arguments passed
        """
        # pylint: disable=broad-except
        try:
            for obj in invoke(self.target, [], input_):
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
