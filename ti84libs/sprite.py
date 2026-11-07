"""Sprites stored in AppVars, built from images by a project's [[tool.tipy.assets]].

An AppVar sprite holds a little-endian 16-bit width and height, then RGB565
pixels. Color 0 is transparent; the converter keeps opaque black visible.
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError
from ti84asm.runtime import LabelRef

from .storage import appvar_label


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    if node.keywords:
        raise CompileError(f"sprite.{method}() uses positional arguments")
    if method == "load":
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            raise CompileError("sprite.load() takes one string literal AppVar name")
        compiler.call_raw("_rt_var_data", [LabelRef(appvar_label(compiler, node.args[0].value.upper()))])
    elif method == "draw":
        if len(node.args) != 3:
            raise CompileError("sprite.draw() takes a sprite, x, and y")
        compiler.call_function("_tipy_sprite_draw", list(node.args))
    else:
        if len(node.args) != 1:
            raise CompileError(f"sprite.{method}() takes one sprite")
        compiler.call_function(f"_tipy_sprite_{method}", list(node.args))
