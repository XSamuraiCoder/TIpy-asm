"""FontLibC font packs on the CE: the FONTPACK AppVars that convfont, and the font asset kind, write.

FontLibC itself draws into GraphX's 8-bit palette screen, and TIpy programs use
the OS's 16-bit color screen, so this library reads the font packs and draws
their glyphs itself. A font is the address of one font in a pack, like a sprite.
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError
from ti84asm.runtime import LabelRef

from .graphics import _color, _default_color
from .storage import appvar_label

_ARITY = {"load": (1, 2), "count": (1,), "height": (1,), "width": (2,), "char": (4, 5)}


def _name(compiler, node: ast.expr, method: str) -> LabelRef:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise CompileError(f"font.{method}() takes the font pack's AppVar name as a string literal")
    return LabelRef(appvar_label(compiler, node.value.upper()))


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    args = list(node.args)
    for keyword in node.keywords:
        if method == "char" and keyword.arg == "color" and len(args) == 4:
            args.append(keyword.value)
        else:
            raise CompileError(f"font.{method}() uses positional arguments")
    if len(args) not in _ARITY[method]:
        raise CompileError(f"font.{method}() takes {' or '.join(map(str, _ARITY[method]))} argument(s)")
    if method == "load":
        compiler.call_function("_tipy_font_load", [_name(compiler, args[0], method), *(args[1:] or [ast.Constant(0)])])
    elif method == "count":
        compiler.call_function("_tipy_font_count", [_name(compiler, args[0], method)])
    elif method == "char":
        color = args[4] if len(args) == 5 else ast.Constant(_default_color(compiler))
        if compiler.constant_integer(color) is not None:
            color = ast.Constant(_color(compiler, color, "font color"))
        compiler.call_function("_tipy_font_char", [*args[:4], color])
    else:
        compiler.call_function(f"_tipy_font_{method}", args)
