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

import argparse
from enum import Enum
from typing import Iterable, List, Tuple
import re

import drgn
import sdb


class MemberExprSep(Enum):
    START = "__start__"
    DOT = "."
    PTR = "->"
    ARRAY = "[]"


class Member(sdb.Command):
    """
    Dereference members of the given structure

    DESCRIPTION
        This is one of main commands used in SDB to explore members of C
        structures and traverse them hierarchically when these structures are
        nested. The notation used for this command is best demonstrated in the
        EXAMPLES section below but in general users should expect the notation
        used in standard C:
        [1] The dot notation/operator `.` can be used reference members in an
            embedded struct.
        [2] `->` can be used to walk into/dereference struct members that are
            pointers.
        [3] Array notation can be used to look into a specific element of an
            array using the index notation. This includes both formally
            specified arrays (like char[100]) and pointers that are used as
            arrays allocated at runtime.

        Something worth noting from a usability perspective for struct members
        that are pointers (see [2] above) is that SDB relaxes the notation and
        allows dereference with the `.` operator too. This means that something
        like this:
            `... | member ptr0->ptr1->ptr2`
        could be also written like this:
            `... | member ptr0.ptr1.ptr2`

    EXAMPLES
        Extract "active_mm" member from "task_struct" structure:

            sdb> addr init_task | member active_mm
            *(struct mm_struct *)0xffff9d0ac59198c0 = {
                    .mmap = (struct vm_area_struct *)0xffff9d0ac47179c0,
            ...

        Examine "active_mm" further by dereferencing its "hmm" member:

            sdb> addr init_task | member active_mm->hmm
            (struct hmm *)0x0

        Even if "active_mm" is a pointer the dot notation can be used in
        SDB and works the same as the previous example:

            sdb> addr init_task | member active_mm.hmm
            (struct hmm *)0x0

        There is no limit theoretically to how deep we can go examining
        nested structures:

            sdb> addr init_task | member active_mm.owner.vmacache
            (struct vmacache){
                    .seqnum = (u64)13,
                    .vmas = (struct vm_area_struct *[4]){
                        0x0, 0xffff9d0ac4717a90, 0xffff9d0ac46cb820,
                    },
            }

        The array notation can be used as in the following example where
        we examine the second element of the "vmas" array from the
        previous example:

            sdb> addr init_task | member active_mm.owner.vmacache.vmas[1]
            *(struct vm_area_struct *)0xffff9d0ac4717a90 = {
                    .vm_start = (unsigned long)140161947738112,
            ...

        Once the array notation has been used we can still continue to
        traverse hierachies (assuming the array elements are structures
        or further array dimensions) like in the example below:

            sdb> addr init_task | member active_mm.owner.vmacache.vmas[1].vm_end
            (unsigned long)93903319175168

        We can also print multiple structure fields with member by
        providing their names separated with spaces. For example below
        we print the "thread" and "mm" members of the "init_task"
        structure:

            sdb> addr init_task | member thread mm
            (struct thread_struct){
                    .tls_array = (struct desc_struct [3]){},
            ...
            (struct mm_struct *)0x0

    """
    # pylint: disable=too-few-public-methods

    names = ["member"]

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument("members", nargs="+", metavar="<member>")
        return parser

    @staticmethod
    def _lex_member_tokens(member_expr: str) -> List[str]:
        """
        Get a member expression and break it up to individual parts/member tokens.
        Example Input: "memberA->memberB[0].memberC"
        Output: ["memberA", "->", "memberB", "[", "0", "]", ".", "memberC"]
        """
        return list(filter(None, re.split(r'(\.|->|\[|\])', member_expr)))

    def _parse_member_tokens(self, tokens: List[str]) -> List[Tuple[str, str]]:
        """
        Iterates through a list of member tokens (generated by _lex_member_tokens()),
        combines these tokens into member terms, and returns a list of all the terms
        or raises a command error if any problem comes up during parsing.

        A member term is a sequence of member tokens grouped together that determine
        the next step of evaluation of the member expression. In this function terms
        are represented by tuples consisting of 2 elements. The first element specifies
        how can we access the subsequent express based on its type (PTR for '->', DOT
        for '.', ARRAY ..etc). The second element holds the name of the object that
        we are about to access (e.g. the name of the field that we are accessing with
        -> or the dot) or the index of element if we are accessing an array.

        To give an example:
        Member Expression -> "memberA->memberB[0].memberC"
        Member Expression Tokens:
            ["memberA", "->", "memberB", "[", "0", "]", ".", "memberC"]
        Member Expression Terms:
            [(START, "memberA"), (PTR, "memberB"), (ARRAY, 0), (DOT, "memberC")]
        """
        terms = []
        while tokens:

            is_index = False
            identifier = ""
            idx = ""
            if tokens[0] == "." or tokens[0] == "->":
                if len(tokens) < 2:
                    raise sdb.CommandError(
                        self.name, f"no identifier specified after {tokens[0]}")
                sep = MemberExprSep(tokens[0])
                identifier = tokens[1]
                tokens = tokens[2:]
            elif tokens[0] == '[':
                if len(tokens) < 3 or tokens[2] != ']':
                    raise sdb.CommandError(
                        self.name, "incomplete array expression: please use " +
                        "something of the format 'array_name[index]'")
                if not tokens[1].isdigit():
                    raise sdb.CommandError(
                        self.name,
                        "incorrect index: '{}' is not a number".format(
                            tokens[1]))
                is_index = True
                idx = tokens[1]
                sep = MemberExprSep.ARRAY
                tokens = tokens[3:]
            else:
                sep = MemberExprSep.START
                identifier = tokens[0]
                tokens = tokens[1:]

            if not is_index and not identifier.isidentifier():
                raise sdb.CommandError(
                    self.name,
                    "{} is not an acceptable identifier".format(identifier))

            if not is_index:
                assert idx == ""
                terms.append((sep, identifier))
            else:
                assert identifier == ""
                terms.append((sep, idx))
        return terms

    @staticmethod
    def _typedef_to_base_kind(type_: drgn.Type) -> drgn.TypeKind:
        while type_.kind == drgn.TypeKind.TYPEDEF:
            type_ = type_.type
        return type_.kind

    def _validate_type_dereference(self, obj: drgn.Object, sep: str) -> None:
        """
        The conventions when dereferencing structure members and array
        elements come straight from the standard C notation:
        [1] The dot notation/operator `.` can be used to reference
            members in an embedded struct.
        [2] `->` can be used to walk/dereference struct members that
            are pointers.
        [3] Array notation can be used to look into a specific element
            of an array using the index notation. This include both
            formally specified arrays (like char[100]) and pointers
            that are used as arrays allocated at runtime.

        Something worth noting from a usability perspective for struct
        members that are pointers (see [2] above) is that SDB relaxes
        the notation and allows dereference with the `.` operator too.
        This means that something like this:
        `... | member ptr0->ptr1->ptr2`
        could be also written like this:
        `... | member ptr0.ptr1.ptr2`
        Besides saving one keystroke, this improves usability as users
        don't have to care about the exact type of the member being a
        struct or a pointer to a struct. This should also help users
        that are switching between DRGN and SDB during development and
        people coming from Acid.
        """
        kind = self._typedef_to_base_kind(obj.type_)

        # This is the first term, no need to do validation.
        if sep == MemberExprSep.START:
            return

        if kind == drgn.TypeKind.STRUCT and sep != MemberExprSep.DOT:
            raise sdb.CommandError(
                self.name,
                "'{}' is a struct - use the dot(.) notation for member access".
                format(obj.type_))

        if kind == drgn.TypeKind.POINTER:
            assert sep in [
                MemberExprSep.PTR, MemberExprSep.DOT, MemberExprSep.ARRAY
            ]
            return

        if kind == drgn.TypeKind.ARRAY and sep != MemberExprSep.ARRAY:
            raise sdb.CommandError(
                self.name, "'{}' is an array - cannot use '{}' notation".format(
                    obj.type_, sep.value))

    def _validate_array_index(self, type_: drgn.Type, idx: int) -> None:
        """
        Array index validation is a lot weaker than the generic type
        validation because of zero-length arrays and pretty-much any
        kind of array allocated on the heap at runtime.

        If we are using the array notation with a pointer, no validation
        happens whatsoever because we can't tell if we are out of bounds
        for something that was allocated at runtime.

        If we are using the array notation on a zero-length array we
        still have the above problem, even though the type comes with
        in size (generally 0 or 1 elements). Because of this reason
        when we encounter an index that is out-of-bounds we print a
        warning and move on instead of raising an error.
        """
        base_kind = Member._typedef_to_base_kind(type_)
        if base_kind == drgn.TypeKind.POINTER:
            return
        assert base_kind == drgn.TypeKind.ARRAY
        if type_.length <= idx:
            warn_msg = f"index out of bounds for array of type '{type_}' (requested index: {idx})"
            print(f"warning: {self.name}: {warn_msg}")

    def _eval_member_terms(self, initial_obj: drgn.Object,
                           terms: List[Tuple[str, str]]
                          ) -> Tuple[drgn.Object, str]:
        """
        Evaluates member terms passed to us by _parse_member_tokens()
        """
        obj = initial_obj
        for term in terms:
            sep, token = term
            self._validate_type_dereference(obj, sep)

            #
            # Ensure we are not trying to dereference NULL.
            #
            if obj.value_() == 0x0:
                warning = f"cannot dereference NULL member of type '{obj.type_}'"
                if not obj.address_ is None:
                    #
                    # This is possible when the object was piped to
                    # us through `echo`.
                    #
                    warning += f" at address {hex(obj.address_of_().value_())}"
                return initial_obj, warning

            if sep == MemberExprSep.ARRAY:
                idx = int(token)
                self._validate_array_index(obj.type_, idx)
                obj = obj[idx]
            else:
                try:
                    obj = obj.member_(token)
                except (LookupError, TypeError) as err:
                    #
                    # The expected error messages that we get from
                    # member_() are good enough to be propagated
                    # as-is.
                    #
                    raise sdb.CommandError(self.name, str(err))
        return obj, ""

    def call(self, objs: Iterable[drgn.Object]) -> Iterable[drgn.Object]:
        for obj in objs:
            for member in self.args.members:
                tokens = Member._lex_member_tokens(member)
                terms = self._parse_member_tokens(tokens)
                resulting_obj, skip_entry_warning = self._eval_member_terms(
                    obj, terms)

                #
                # In some cases it would be annoying to stop a pipeline
                # mid-way just because a member is NULL. At the same time
                # it could be misleading in cases where a NULL is not
                # expected but it exists (e.g. let's say due to a bug).
                # As a trade-off between the two above cases, we allow
                # pipelines to proceed but we always print a warning
                # that a NULL was encountered.
                #
                if skip_entry_warning:
                    print(f"warning: {self.name}: {skip_entry_warning}")
                    continue
                yield resulting_obj
