"""Font library for TIpy-asm.

Provides font handling similar to CEdev's fontlibc, for working with
fonts converted via convfont (FontLibC .fnt format).

Usage:
    from ti84 import font
    
    # Load a font from an AppVar
    my_font = font.load("FONTDATA")
    
    # Draw text with the font
    font.draw_text(my_font, "Hello!", x=10, y=10, color=font.BLACK)
    
    # Get font metrics
    width = font.string_width(my_font, "Hello!")
    height = font.height(my_font)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ti84asm.errors import CompileError


# FontLibC color constants (RGB565)
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
YELLOW = 0xFFE0
CYAN = 0x07FF
MAGENTA = 0xF81F
ORANGE = 0xFD20
PURPLE = 0x801F
GRAY = 0x8410


@dataclass
class Font:
    """Represents a loaded FontLibC font."""
    # AppVar name where font data is stored
    appvar_name: str
    # Offset in AppVar (0 for single font file)
    offset: int = 0
    # Font metadata will be parsed from the .fnt header


# FontLibC header structure (first 16 bytes)
# typedef struct {
#     uint8_t signature[8];     // "FNTxxxxx" where xxxxx is version
#     uint8_t height;           // Font height in pixels
#     uint8_t baseline;         // Baseline position
#     uint8_t caps_height;      // Capital letter height
#     uint8_t reserved;        // Reserved
#     uint16_t chars_count;     // Number of characters
#     uint8_t bpp;             // Bits per pixel (1, 2, 4, or 8)
#     uint8_t encoding;         // 0=ASCII, 1=UTF-8
# } fontlib_font_t;

FONT_SIGNATURE = b"FNT"


# Public API for the assembly backend
ASSEMBLY_API = {
    "load",
    "draw_char", 
    "draw_text",
    "char_width",
    "string_width",
    "height",
    "baseline",
}


def _emit_load(compiler, appvar_name_node: ast.expr) -> None:
    """Load font data from an AppVar."""
    if not isinstance(appvar_name_node, ast.Constant) or not isinstance(appvar_name_node.value, str):
        raise CompileError("font.load() requires a string literal AppVar name")
    
    name = appvar_name_node.value
    if not 1 <= len(name) <= 8 or not name.isalnum():
        raise CompileError("AppVar names are 1-8 alphanumeric characters")
    
    if compiler.target == "ce":
        # CE: Use OS AppVar access
        compiler.emit(f"    ld hl,{name}")
        compiler.emit("    call ti.os.GetAppVarData")
        compiler.emit("    jr nc,font_not_found")
        # HL now points to AppVar data
        # TODO: Parse header and store font info
        compiler.emit("    ; Font loaded successfully")
    else:
        # Classic: Not supported yet
        raise CompileError("font.load() requires CE target")


def _emit_draw_char(compiler, node: ast.Call) -> None:
    """Draw a single character from a font."""
    # font.draw_char(font, char, x, y, color=BLACK)
    if len(node.args) not in (4, 5) or node.keywords:
        raise CompileError("draw_char() takes font, char, x, y, and optional color")
    
    # For now, emit a placeholder
    if compiler.target == "ce":
        compiler.emit("    ; font.draw_char() - TODO: implement")
    else:
        raise CompileError("font.draw_char() requires CE target")


def _emit_draw_text(compiler, node: ast.Call) -> None:
    """Draw text using a font."""
    # font.draw_text(font, text, x, y, color=BLACK)
    if len(node.args) not in (4, 5) or node.keywords:
        raise CompileError("draw_text() takes font, text, x, y, and optional color")
    
    if not isinstance(node.args[1], ast.Constant) or not isinstance(node.args[1].value, str):
        raise CompileError("draw_text() requires a string literal")
    
    if compiler.target == "ce":
        # Use OS font drawing for now
        text = node.args[1].value
        try:
            encoded = text.encode("ascii") + b"\0"
        except UnicodeEncodeError as exc:
            raise CompileError("draw_text() supports ASCII strings only") from exc
        
        string_label = compiler.label("font_text")
        compiler.data_bytes(string_label, list(encoded))
        
        x = compiler.constant_integer(node.args[2])
        y = compiler.constant_integer(node.args[3])
        
        if x is None or y is None:
            raise CompileError("draw_text() requires constant coordinates for now")
        
        color = node.args[4] if len(node.args) == 5 else ast.Constant(value=BLACK)
        color_val = _color(compiler, color)
        
        red = (color_val >> 11) & 0x1F
        green = (color_val >> 5) & 0x3F
        blue = color_val & 0x1F
        os_color = (blue << 11) | (green << 5) | red
        
        compiler.emit(f"    ld hl,{os_color}")
        compiler.emit("    push hl")
        compiler.emit("    call ti.os.SetDrawFGColor")
        compiler.emit("    pop hl")
        compiler.emit(f"    ld hl,{y}")
        compiler.emit("    push hl")
        compiler.emit(f"    ld hl,{x}")
        compiler.emit("    push hl")
        compiler.emit(f"    ld hl,{string_label}")
        compiler.emit("    push hl")
        compiler.emit("    call ti.os.FontDrawText")
        compiler.emit("    ld hl,9")
        compiler.emit("    add hl,sp")
        compiler.emit("    ld sp,hl")
    else:
        raise CompileError("font.draw_text() requires CE target")


def _emit_char_width(compiler, node: ast.Call) -> None:
    """Get width of a character in a font."""
    if len(node.args) != 2 or node.keywords:
        raise CompileError("char_width() takes font and char")
    
    if compiler.target == "ce":
        compiler.emit("    ; font.char_width() - TODO: implement")
    else:
        raise CompileError("font.char_width() requires CE target")


def _emit_string_width(compiler, node: ast.Call) -> None:
    """Get width of a string in a font."""
    if len(node.args) != 2 or node.keywords:
        raise CompileError("string_width() takes font and text")
    
    if not isinstance(node.args[1], ast.Constant) or not isinstance(node.args[1].value, str):
        raise CompileError("string_width() requires a string literal")
    
    # For now, estimate based on string length * 8 (approximate)
    text = node.args[1].value
    width = len(text) * 8
    compiler.emit(f"    ld hl,{width}")


def _emit_height(compiler, node: ast.Call) -> None:
    """Get font height."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("height() takes font")
    
    # Default font height
    compiler.emit("    ld hl,16")  # Assume 16px font


def _emit_baseline(compiler, node: ast.Call) -> None:
    """Get font baseline position."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("baseline() takes font")
    
    # Default baseline
    compiler.emit("    ld hl,12")  # Assume 12px baseline for 16px font


def _color(compiler, node: ast.expr) -> int:
    """Convert a color expression to RGB565."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "font" and hasattr(font, node.attr.upper()):
            return getattr(font, node.attr.upper())
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value & 0xFFFF
    raise CompileError("Invalid color expression")


def emit_call(compiler, node: ast.Call) -> None:
    """Emit a font library call."""
    if not isinstance(node.func, ast.Attribute):
        raise CompileError("font calls must use a font library name")
    
    method = node.func.attr
    
    if method == "load":
        _emit_load(compiler, node.args[0] if node.args else None)
    elif method == "draw_char":
        _emit_draw_char(compiler, node)
    elif method == "draw_text":
        _emit_draw_text(compiler, node)
    elif method == "char_width":
        _emit_char_width(compiler, node)
    elif method == "string_width":
        _emit_string_width(compiler, node)
    elif method == "height":
        _emit_height(compiler, node)
    elif method == "baseline":
        _emit_baseline(compiler, node)
    else:
        supported = ", ".join(f"font.{name}()" for name in sorted(ASSEMBLY_API))
        raise CompileError(f"font library supports {supported}")
