# Usage: IDALOG=/dev/stdout ./idat64 -B -S/path/to/collect.py /path/to/binary

from collections import defaultdict
from util import UNDEF_ADDR, CFuncTree, CFuncTreeBuilder, get_expr_name
import typeinfo as ti
import typing as t
import idaapi
from idautils import Functions
import ida_auto
import ida_funcs
import ida_hexrays
import ida_kernwin
import ida_pro
import ida_struct
import pickle
import os
import yaml
import json

import typing as t


# class CollectTree(CFuncTree):
#     """Collects a map of a set of addresses to a variable name.
#     For each variable, this collects the addresses corresponding to its uses.

#     Attributes
#     user_locals: List of names of user-defined locals in this function
#     varmap: Dictionary mapping frozensets of addresses to variable names
#     """

#     def __init__(self, user_locals, varmap):
#         self.user_locals = user_locals
#         self.varmap = varmap
#         super().__init__()

#     def collect_vars(self):
#         rev_dict = defaultdict(set)
#         for n in range(len(self.items)):
#             item = self.items[n]
#             if item.op is ida_hexrays.cot_var:
#                 name = get_expr_name(item.cexpr)
#                 if name in self.user_locals:
#                     if item.ea != UNDEF_ADDR:
#                         rev_dict[name].add(item.ea)
#                     else:
#                         ea = self.get_pred_ea(n)
#                         if ea != UNDEF_ADDR:
#                             rev_dict[name].add(ea)
#         # ::NONE:: is a sentinel value used to indicate that two different
#         # variables map to the same set of addresses. This happens in small
#         # functions that use all of their arguments to call another function.
#         for name, addrs in rev_dict.items():
#             addrs = frozenset(addrs)
#             if addrs in self.varmap:
#                 print("collision")
#                 print(f"current: {self.varmap[addrs]}")
#                 print(f"new: {name}")
#                 self.varmap[addrs] = "::NONE::"
#             else:
#                 self.varmap[addrs] = name


class Collector(ida_kernwin.action_handler_t):
    def __init__(self):
        # eas -> list of user defined locals
        self.fun_locals: t.DefaultDict[int, t.List[str]] = defaultdict(list)
        try:
            with open(os.environ["TYPE_LIB"], "rb") as type_lib_file:
                self.type_lib = ti.TypeLibCodec.decode(type_lib_file.read())
        except Exception as e:
            print("Could not find type library, creating a new one")
            self.type_lib = ti.TypeLib()
        ida_kernwin.action_handler_t.__init__(self)

    def dump_info(self) -> None:
        """Dumps the collected variables and function locals to the files
        specified by the environment variables `COLLECTED_VARS` and
        `FUN_LOCALS` respectively.
        """
        print(f"{self.type_lib}")
        with open(os.environ["FUN_LOCALS"], "wb") as locals_fh, open(
            os.environ["TYPE_LIB"], "w"
        ) as type_lib_fh:
            pickle.dump(self.fun_locals, locals_fh)
            type_lib_fh.write(ti.TypeLibCodec.encode(self.type_lib))
            locals_fh.flush()
            type_lib_fh.flush()

    def activate(self, ctx) -> int:
        """Collects types, user-defined variables, and their locations"""
        print("Collecting vars and types.")
        # `ea` is the start address of a single function
        for ea in Functions():
            f = idaapi.get_func(ea)
            cfunc = None
            try:
                cfunc = idaapi.decompile(f)
            except ida_hexrays.DecompilationFailure:
                continue
            if cfunc is None:
                continue
            function_name = ida_funcs.get_func_name(ea)
            user_var_locations: t.List[t.Tuple[str, int]] = list()
            # print(dir(cfunc))
            for v in cfunc.arguments:
                if v.name == "":
                    continue
                if v.type():
                    self.type_lib.add_ida_type(v.type())
                    var_location: str
                    if v.is_stk_var():
                        corrected = v.get_stkoff() - cfunc.get_stkoff_delta()
                        var_offset = f.frsize - corrected
                        var_location = f"BP offset {var_offset}"
                    if v.is_reg_var():
                        var_location = f"Register {v.get_reg1()}"
                # print(f"Arg: {v.name.strip()} {var_location}")
            # Collect the locations and types of the stack variables
            for v in list(cfunc.get_lvars()) + list(cfunc.arguments):
                if v.name == "" or not v.has_user_name:
                    continue
                if v.type():
                    self.type_lib.add_ida_type(v.type())
                    # Only save variables with user names
                    if v.has_user_name:
                        var_location: str
                        if v.is_stk_var():
                            corrected = v.get_stkoff() - cfunc.get_stkoff_delta()
                            var_offset = f.frsize - corrected
                            var_location = f"BP offset {var_offset}"
                        if v.is_reg_var():
                            var_location = f"Register {v.get_reg1()}"
                    # print(f"Var: {v.name.strip()} {var_location}")
            cur_locals = [
                v.name for v in cfunc.get_lvars() if v.has_user_name and v.name != ""
            ]
            # print(cfunc)
            # print("----------------------------------------")
            if cur_locals == []:
                continue
            self.fun_locals[ea] = cur_locals
        self.dump_info()
        return 1


ida_auto.auto_wait()
if not idaapi.init_hexrays_plugin():
    idaapi.load_plugin("hexrays")
    idaapi.load_plugin("hexx64")
    if not idaapi.init_hexrays_plugin():
        print("Unable to load Hex-rays")
        ida_pro.qexit(1)
    else:
        print(f"Hex-rays version {idaapi.get_hexrays_version()}")

cv = Collector()
cv.activate(None)
ida_pro.qexit(0)
