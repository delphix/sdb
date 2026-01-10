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

from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class Table:
    """
    Generic Table implementation for pretty-printing
    data in columns.
    """

    __slots__ = "fields", "rjustfields", "formatters", "maxfieldlen", "lines"

    def __init__(
            self,
            fields: List[str],
            rjustfields: Optional[Set[str]] = None,
            formatters: Optional[Dict[str, Callable[[Any],
                                                    str]]] = None) -> None:
        self.fields = fields

        if rjustfields is None:
            self.rjustfields: Set[str] = set()
        else:
            self.rjustfields = rjustfields

        if formatters is None:
            self.formatters: Dict[str, Callable[[Any], str]] = {}
        else:
            to_str: Callable[[Any], str] = str
            self.formatters = {
                field:
                (formatters[field] if field in formatters.keys() else to_str)
                for field in fields
            }

        self.maxfieldlen = dict.fromkeys(fields, 0)
        self.lines: List[Tuple[Any, List[str]]] = []

    def add_row(self, sortkey: Any, values: Dict[str, Any]) -> None:
        row_values = []
        for field in self.fields:
            val = self.formatters[field](values[field])
            row_values.append(val)
            self.maxfieldlen[field] = max(self.maxfieldlen[field], len(val))
        self.lines.append((sortkey, row_values))

    def print_(self,
               print_headers: bool = True,
               reverse_sort: bool = False) -> None:
        delimeter = "\t"
        if print_headers:
            delimeter = " "
            headers, separators = [], []
            for field in self.fields:
                self.maxfieldlen[field] = max(self.maxfieldlen[field],
                                              len(field))
                if field in self.rjustfields:
                    headers.append(f"{field:>{self.maxfieldlen[field]}}")
                else:
                    headers.append(f"{field:<{self.maxfieldlen[field]}}")
                separators.append('-' * self.maxfieldlen[field])
            print(delimeter.join(headers))
            print(delimeter.join(separators))

        self.lines.sort(reverse=reverse_sort)
        for _, row_values in self.lines:
            if not print_headers:
                print(delimeter.join(row_values))
                continue

            line_fields = []
            for fid, field in enumerate(self.fields):
                if field in self.rjustfields:
                    line_fields.append(
                        f"{row_values[fid]:>{self.maxfieldlen[field]}}")
                else:
                    line_fields.append(
                        f"{row_values[fid]:<{self.maxfieldlen[field]}}")
            print(delimeter.join(line_fields))
