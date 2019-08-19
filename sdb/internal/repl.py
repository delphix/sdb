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

import sdb


# pylint: disable=too-few-public-methods
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

    def __init__(self, target, vocabulary, prompt="> ", closing=""):
        self.prompt = prompt
        self.closing = closing
        self.vocabulary = vocabulary
        self.target = target

        histfile = os.path.expanduser('~/.sdb_history')
        try:
            readline.read_history_file(histfile)
        except FileNotFoundError:
            pass

        readline.parse_and_bind("tab: complete")
        readline.set_history_length(1000)
        readline.set_completer(REPL.__make_completer(vocabulary))

        atexit.register(readline.write_history_file, histfile)

    def run(self):
        """
        Starts a REPL session.
        """
        while True:
            try:
                line = input(self.prompt).strip()
                if not line:
                    continue

                objs = sdb.invoke(self.target, [], line)
                if not objs:
                    continue

                for obj in objs:
                    print(obj)

            except sdb.CommandArgumentsError:
                #
                # We skip printing anything for this specific error
                # as argparse should have already printed a helpful
                # message to the REPL for us.
                #
                continue
            except sdb.Error as err:
                print(err.text)
            except (EOFError, KeyboardInterrupt):
                print(self.closing)
                break
