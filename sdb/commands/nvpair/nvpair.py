#
# Copyright 2020 Datto, Inc.
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

import os
import drgn
import sdb


class Nvpair:
    # Member data and methods to print the value of the
    # various nvpair_t types
    def __init__(self, nvp: drgn.Object, nvl: drgn.Object) -> None:
        self.addr = nvp.address_
        self.nvp = nvp
        self.nvl = nvl
        self.nvp_size_ = sdb.type_canonicalize_size("nvpair_t")
        self.nvl_size = sdb.type_canonicalize_size("nvlist_t")
        self.name_size = int(nvp.nvp_name_sz)
        self.data_ptr = self.addr + ((self.nvp_size_ + self.name_size + 7) & ~7)

    def get_type(self, strip: bool = False) -> str:
        # N.B. data_type_t enum is not zero indexed it starts
        # with -1 so we add one to get the correct index
        fields = sdb.get_type("data_type_t").type.enumerators
        enum_string: str = fields[self.nvp.nvp_type + 1].name
        if strip:
            prefix = os.path.commonprefix([f[0] for f in fields])
            return enum_string[prefix.rfind("_") + 1:]
        return enum_string

    def get_name(self) -> drgn.Object:
        # name is located after the nvpair_t struct
        ptr = self.addr + self.nvp_size_
        return sdb.create_object("char *", ptr).string_().decode("utf-8")

    # works for all signed and unsigned int, long, long long
    @staticmethod
    def get_value_int(type_: str, loc: int) -> str:
        sz = sdb.create_object('size_t', sdb.type_canonicalize_size(type_))
        # value is located after the name
        contents = sdb.get_prog().read(loc, sz)
        value = drgn.Object.from_bytes_(sdb.get_prog(), type_, contents)
        return str(value.value_())

    # iterate the array, obtain and print nvpair values
    def get_array_values(self, type_: str) -> None:
        indent = "    "
        count = self.nvp.nvp_value_elem
        type_ = type_.replace("_array", "")
        if "boolean" in type_:
            type_ = "uint32_t"
        val = ""
        # skip n 64 bit pointers for string and nvlist array type
        offset = count * 8
        for x in range(count):
            if x == 0:
                print("values=")
            if "nvlist" in type_:
                self.nvl.set_indent(self.nvl.indent + 4)
                self.nvl.print_one(
                    sdb.create_object("nvlist_t *", self.data_ptr + offset))
                self.nvl.set_indent(self.nvl.indent - 4)
                offset += self.nvl_size
            elif "int" in type_:
                sz = sdb.create_object('size_t',
                                       sdb.type_canonicalize_size(type_))
                val = self.get_value_int(type_, self.data_ptr + (sz * x))
                print(f"{indent}{val}")
            elif "byte" in type_:
                val = self.get_value_int("unsigned char", self.data_ptr + x)
                print(f"{indent}{hex(int(val))}")
            elif "string" in type_:
                offset += len(val)
                val = sdb.create_object("char *", self.data_ptr +
                                        offset).string_().decode("utf-8")
                print(f"{indent}{val}")
                offset += 1  # null terminator

    # obtain and print the nvpair value
    def get_value(self) -> None:
        type_ = (self.get_type(True) + "_t").lower()
        if "array" in type_:
            self.get_array_values(type_)
            return
        if "nvlist" in type_:
            print("values=")
            self.nvl.set_indent(self.nvl.indent + 4)
            self.nvl.print_one(sdb.create_object("nvlist_t *", self.data_ptr))
            self.nvl.set_indent(self.nvl.indent - 4)
            return
        print("value=", end='')
        if "boolean_value" in type_:
            type_ = "uint32_t"
        elif "boolean" in type_:  # DATA_TYPE_BOOLEAN has name and no value
            print("")
        elif "hrtime" in type_:
            type_ = "int64_t"
        if "int" in type_:
            print(self.get_value_int(type_, self.data_ptr))
        if "string" in type_:
            print(
                sdb.create_object("char *",
                                  self.data_ptr).string_().decode("utf-8"))
        if "byte" in type_:
            print(hex(int(self.get_value_int("unsigned char", self.data_ptr))))
        return


class Nvlist(sdb.SingleInputCommand):
    """
    Print nvlist_t

    DESCRIPTION
        Print all the nvpair_t in the passed nvlist_t.  Handle basic types,
        array types, and nvlist_t types.  Type double is omitted as it is
        not used in zfs.

    EXAMPLE
    Print nvlist_t of snapshot holds from the nvlist_t * pointer address:

        sdb> echo 0xffff970d0ff681e0 | nvlist
        name=monday-1 type=DATA_TYPE_UINT64 value=1633989858
        name=monday-2 type=DATA_TYPE_UINT64 value=1633989863
    """

    names = ["nvlist"]
    input_type = "nvlist_t *"
    output_type = "nvlist_t *"
    indent = 0

    def set_indent(self, indent: int) -> None:
        self.indent = indent

    # nvlist iteration methods
    @staticmethod
    def nvlist_contains_nvp(nvl: drgn.Object, nvp: drgn.Object) -> int:
        priv = drgn.cast("nvpriv_t *", nvl.nvl_priv)
        if nvp.address_ == 0:
            return 0

        curr = priv.nvp_list
        while not sdb.is_null(curr):
            if curr.nvi_nvp.address_ == nvp.address_:
                return 1
            # pylint: disable=protected-access
            curr = curr._nvi_un._nvi._nvi_next

        return 0

    @staticmethod
    def nvlist_first_nvpair(nvl: drgn.Object) -> drgn.Object:
        if sdb.is_null(nvl) or sdb.is_null(nvl.nvl_priv):
            return None
        priv = drgn.cast("nvpriv_t *", nvl.nvl_priv)
        if sdb.is_null(priv.nvp_list):
            return None
        return priv.nvp_list.nvi_nvp

    @staticmethod
    def nvlist_next_nvpair(nvl: drgn.Object, nvp: drgn.Object) -> drgn.Object:
        if sdb.is_null(nvl) or sdb.is_null(nvl.nvl_priv):
            return None

        priv = drgn.cast("nvpriv_t *", nvl.nvl_priv)

        curr_addr = nvp.address_ - drgn.offsetof(sdb.get_type("i_nvp_t"),
                                                 "nvi_nvp")
        curr = sdb.create_object("i_nvp_t *", curr_addr)

        if priv.nvp_curr == curr or Nvlist.nvlist_contains_nvp(nvl, nvp):
            # pylint: disable=protected-access
            curr = curr._nvi_un._nvi._nvi_next
        else:
            curr = drgn.NULL(sdb.get_prog(), "i_nvp_t *")

        if not sdb.is_null(curr):
            return curr.nvi_nvp

        return None

    # print one nvlist_t
    def print_one(self, nvl: drgn.Object) -> None:
        pair = self.nvlist_first_nvpair(nvl)
        while pair is not None:
            nvobj = Nvpair(pair, self)
            print(f"{' '*self.indent}", end='')
            print(f"name={nvobj.get_name()} ", end='')
            print(f"type={nvobj.get_type()} ", end='')
            # value will be printed in get_value function
            nvobj.get_value()
            pair = self.nvlist_next_nvpair(nvl, pair)

    def _call_one(self, obj: drgn.Object) -> None:
        self.print_one(obj)
        print("----")
