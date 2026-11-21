"""FontLibC font packs on the CE: the FONTPACK AppVars that convfont, and the font asset kind, write.

FontLibC itself draws into GraphX's 8-bit palette screen, and TIpy programs use
the OS's 16-bit color screen, so this library reads the font packs and draws
their glyphs itself. A font is the address of one font in a pack, and a pack is
the address of a pack's data: load() and friends take a pack's AppVar name as a
string literal, or a pack that find() returned. Text is a string literal, the
address of text (such as family()'s), or a module-level int array of character
codes, of which start= and count= pick a part.
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError
from ti84asm.runtime import LabelRef

from .graphics import _color, _default_color
from .storage import appvar_label

# FontLibC's weights and styles (fontlibc.h), for by_style().
CONSTANTS = {
    "THIN": 0x20, "EXTRA_LIGHT": 0x30, "LIGHT": 0x40, "SEMILIGHT": 0x60, "NORMAL": 0x80, "MEDIUM": 0x90,
    "SEMIBOLD": 0xA0, "BOLD": 0xC0, "EXTRA_BOLD": 0xE0, "HEAVY": 0xF0,
    "SERIF": 0x01, "OBLIQUE": 0x02, "ITALIC": 0x04, "MONOSPACED": 0x08,
}

_ARITY = {"default": (0,), "load": (1, 2), "count": (1,), "find": (0, 1), "family": (1,), "by_style": (7,),
          "height": (1,), "width": (2,), "char": (4, 5), "text": (4, 5, 6), "text_width": (2,),
          "paragraph": (5, 6, 7)}
# Keywords that may also be given by position, in order, after the positional ones.
_KEYWORDS = {"char": ("color",), "text": ("color", "background"), "paragraph": ("color", "background")}
_POSITIONS = {"char": 4, "text": 4, "paragraph": 5}
# Keywords for text kept in an int array.
_ARRAY_KEYWORDS = {"text": ("start", "count"), "text_width": ("start", "count")}


def constant(name: str) -> int | None:
    return CONSTANTS.get(name)


def default_font_label(compiler) -> str:
    from .fontdata import font_bytes

    cached = getattr(compiler, "_default_font", None)
    if cached is None or cached[0] is not compiler.data:
        label = compiler.label("font_default")
        compiler.data_bytes(label, list(font_bytes()))
        compiler._default_font = (compiler.data, label)
    return compiler._default_font[1]


def _is_text(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _name(compiler, node: ast.expr) -> LabelRef:
    return LabelRef(appvar_label(compiler, node.value.upper()))


def _text(compiler, node: ast.expr) -> ast.expr:
    """A string literal becomes its address; anything else is already an address."""
    if _is_text(node):
        return LabelRef(compiler.string_label(node.value, "font text"))
    return node


def _array(compiler, node: ast.expr) -> tuple[str, int] | None:
    """(label, length) when node names a module-level int array of character codes."""
    if isinstance(node, ast.Name) and isinstance(compiler.constants.get(node.id), (ast.List, ast.Tuple)):
        return compiler._array(node.id)
    return None


def _paint(compiler, node: ast.expr | None, default: int) -> ast.expr:
    if node is None:
        return ast.Constant(default)
    value = compiler.constant_integer(node)
    if value is None or value < 0:
        return node
    return ast.Constant(_color(compiler, node, "font color"))


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    args = list(node.args)
    named, span = {}, {}
    for keyword in node.keywords:
        if keyword.arg in _ARRAY_KEYWORDS.get(method, ()):
            span[keyword.arg] = keyword.value
            continue
        if keyword.arg not in _KEYWORDS.get(method, ()):
            raise CompileError(f"font.{method}() has no keyword {keyword.arg}")
        named[keyword.arg] = keyword.value
    for offset, keyword in enumerate(_KEYWORDS.get(method, ())):
        if keyword in named:
            if len(args) != _POSITIONS[method] + offset:
                raise CompileError(f"font.{method}() got {keyword} twice, or out of order")
            args.append(named[keyword])
    if len(args) not in _ARITY[method]:
        raise CompileError(f"font.{method}() takes {' or '.join(map(str, _ARITY[method]))} argument(s)")

    if method == "default":
        # The built-in font goes in the program once, so it needs no AppVar.
        compiler.emit(f"    ld hl,{default_font_label(compiler)}")
    elif method == "load":
        index = args[1:] or [ast.Constant(0)]
        if _is_text(args[0]):
            compiler.call_function("_tipy_font_load", [_name(compiler, args[0]), *index])
        else:
            compiler.call_function("_tipy_font_in", [args[0], *index])
    elif method == "count":
        if _is_text(args[0]):
            compiler.call_function("_tipy_font_count", [_name(compiler, args[0])])
        else:
            compiler.call_function("_tipy_font_count_in", args)
    elif method == "find":
        compiler.call_function("_tipy_font_find", args or [ast.Constant(0)])
    elif method == "by_style":
        if _is_text(args[0]):
            compiler.call_function("_tipy_font_by_style_named", [_name(compiler, args[0]), *args[1:]])
        else:
            compiler.call_function("_tipy_font_by_style", args)
    elif method == "char":
        color = _paint(compiler, args[4] if len(args) == 5 else None, _default_color(compiler))
        compiler.call_raw("_rt_font_glyph", [*args[:4], color])
    elif method in ("text", "text_width"):
        array = _array(compiler, args[1])
        if span and array is None:
            raise CompileError(f"font.{method}() takes start= and count= only for text in an int array")
        if method == "text":
            color = _paint(compiler, args[4] if len(args) > 4 else None, _default_color(compiler))
            background = _paint(compiler, args[5] if len(args) > 5 else None, -1)
            if array is None:
                compiler.call_function("_tipy_font_text", [args[0], _text(compiler, args[1]), args[2], args[3],
                                                           color, background])
            else:
                label, length = array
                compiler.call_function("_tipy_font_array", [args[0], LabelRef(label), ast.Constant(length),
                                                            span.get("start", ast.Constant(0)),
                                                            span.get("count", ast.Constant(-1)),
                                                            args[2], args[3], color, background])
        elif array is None:
            compiler.call_function("_tipy_font_text_width", [args[0], _text(compiler, args[1])])
        else:
            label, length = array
            compiler.call_function("_tipy_font_array_width", [args[0], LabelRef(label), ast.Constant(length),
                                                              span.get("start", ast.Constant(0)),
                                                              span.get("count", ast.Constant(-1))])
    elif method == "paragraph":
        color = _paint(compiler, args[5] if len(args) > 5 else None, _default_color(compiler))
        background = _paint(compiler, args[6] if len(args) > 6 else None, -1)
        compiler.call_function("_tipy_font_paragraph", [args[0], _text(compiler, args[1]), args[2], args[3],
                                                        args[4], color, background])
    else:
        compiler.call_function(f"_tipy_font_{method}", args)