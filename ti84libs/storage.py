"""Persistent byte storage using TI AppVars. Also serves as ``ti84.file`` on assembly."""

from __future__ import annotations

import ast
import re

from ti84asm.errors import CompileError
from ti84asm.runtime import LabelRef

ARITY = {"create": 2, "exists": 1, "size": 1, "delete": 1, "clear": 1, "read_byte": 2, "write_byte": 3,
         "read_u16": 2, "write_u16": 3}
_RAW = {"create": "_rt_var_create", "exists": "_rt_var_exists", "size": "_rt_var_size", "delete": "_rt_var_delete",
        "read_byte": "_rt_var_read", "write_byte": "_rt_var_write"}
_PRELUDE = {"clear": "_tipy_file_clear", "read_u16": "_tipy_read_u16", "write_u16": "_tipy_write_u16"}


def appvar_label(compiler, name: str) -> str:
    """Return the label of an AppVar's OP1-format name, sharing repeats."""
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", name):
        raise CompileError("AppVar names must be 1-8 uppercase ASCII letters/digits")
    if name not in compiler.appvar_labels:
        label = compiler.label("appvar")
        compiler.appvar_labels[name] = label
        bytestr = ",".join(compiler.byte_literal(ord(ch)) for ch in name + "\0")
        object_type = "AppVarObj" if compiler.target == "classic" else "ti.AppVarObj"
        compiler.data.append(f"{label}: {compiler.directive('db')} {object_type},{bytestr}")
    return compiler.appvar_labels[name]


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    if node.keywords:
        raise CompileError("storage methods use positional arguments only")
    if len(node.args) != ARITY[method]:
        raise CompileError(f"{method}() takes {ARITY[method]} arguments, starting with the AppVar name")
    if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        raise CompileError("storage methods require an AppVar name string as the first argument")
    name = LabelRef(appvar_label(compiler, node.args[0].value.upper()))
    arguments = [name, *node.args[1:]]
    if method == "create":
        size = compiler.constant_integer(node.args[1])
        if size is not None and size < 1:
            raise CompileError("AppVar size must be at least 1 byte")
    if method in ("read_byte", "write_byte"):
        offset = compiler.constant_integer(node.args[1])
        if offset is not None and offset < 0:
            raise CompileError("AppVar offset cannot be negative")
    if method == "write_byte":
        value = compiler.constant_integer(node.args[2])
        if value is not None and not 0 <= value <= 255:
            raise CompileError("byte value must be in the range 0..255")
    if method in _PRELUDE:
        compiler.call_function(_PRELUDE[method], arguments)
    else:
        compiler.call_raw(_RAW[method], arguments)
