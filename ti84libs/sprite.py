"""Sprites stored in AppVars, built from images by a project's [[tool.tipy.assets]].

An AppVar sprite holds a little-endian 16-bit width and height, then RGB565
pixels. Color 0 is transparent; the converter keeps opaque black visible. A pack
is several sprites one after another in one AppVar, so a single sprite is a pack
of one.
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
        if (len(node.args) not in (1, 2) or not isinstance(node.args[0], ast.Constant)
                or not isinstance(node.args[0].value, str)):
            raise CompileError("sprite.load() takes a string literal AppVar name and an optional index")
        name = LabelRef(appvar_label(compiler, node.args[0].value.upper()))
        if len(node.args) == 1:
            compiler.call_raw("_rt_var_data", [name])
        else:
            # Sprite number `index` of a pack: sprites one after another in one AppVar.
            compiler.call_function("_tipy_sprite_load", [name, node.args[1]])
    elif method == "draw":
        if len(node.args) != 3:
            raise CompileError("sprite.draw() takes a sprite, x, and y")
        compiler.call_function("_tipy_sprite_draw", list(node.args))
    else:
        if len(node.args) != 1:
            raise CompileError(f"sprite.{method}() takes one sprite")
        compiler.call_function(f"_tipy_sprite_{method}", list(node.args))
