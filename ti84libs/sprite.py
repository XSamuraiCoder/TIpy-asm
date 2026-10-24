"""Sprite library for TIpy-asm.

Provides enhanced sprite handling for TI calculators, similar to CEdev's
graphx sprite functions. Supports loading sprites from AppVars and
drawing them with transparency.

Usage:
    from ti84 import sprite
    
    # Load sprite from AppVar
    my_sprite = sprite.load("SPRITEDATA")
    
    # Draw sprite
    sprite.draw(my_sprite, x=10, y=10)
    
    # Draw with scaling
    sprite.draw_scale(my_sprite, x=10, y=10, scale_x=2, scale_y=2)
    
    # Get sprite dimensions
    width, height = sprite.dimensions(my_sprite)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ti84asm.errors import CompileError


@dataclass
class Sprite:
    """Represents a loaded sprite."""
    # AppVar name where sprite data is stored
    appvar_name: str
    # Sprite width in pixels
    width: int
    # Sprite height in pixels
    height: int
    # Pixel format: "rgb565" or "palette"
    format: str = "rgb565"
    # For palette format, the palette AppVar name
    palette: str | None = None


# Sprite data formats
FORMAT_RGB565 = "rgb565"  # 16-bit RGB565 (2 bytes per pixel)
FORMAT_PALETTE = "palette"  # 8-bit palette index (1 byte per pixel)


# Public API for the assembly backend
ASSEMBLY_API = {
    "load",
    "draw",
    "draw_scale",
    "draw_rotate",
    "dimensions",
    "get_pixel",
    "set_pixel",
}


def _emit_load(compiler, node: ast.Call) -> None:
    """Load sprite data from an AppVar."""
    if not node.args or len(node.args) > 2:
        raise CompileError("sprite.load() takes AppVar name and optional palette name")
    
    appvar_name_node = node.args[0]
    if not isinstance(appvar_name_node, ast.Constant) or not isinstance(appvar_name_node.value, str):
        raise CompileError("sprite.load() requires a string literal AppVar name")
    
    name = appvar_name_node.value
    if not 1 <= len(name) <= 8 or not name.isalnum():
        raise CompileError("AppVar names are 1-8 alphanumeric characters")
    
    if compiler.target == "ce":
        # Load AppVar data
        compiler.emit(f"    ld hl,{name}")
        compiler.emit("    call ti.os.GetAppVarData")
        compiler.emit("    jr nc,sprite_not_found")
        # HL points to AppVar data
        # Store pointer for later use
        compiler.emit(f"    ld ({compiler.label('sprite_ptr')}),hl")
    else:
        raise CompileError("sprite.load() requires CE target")


def _emit_draw(compiler, node: ast.Call) -> None:
    """Draw a sprite at specified coordinates."""
    if len(node.args) not in (2, 3) or node.keywords:
        raise CompileError("draw() takes sprite, x, and optional y")
    
    x = compiler.constant_integer(node.args[1])
    y = compiler.constant_integer(node.args[2]) if len(node.args) == 3 else None
    
    if compiler.target == "ce":
        if x is None or y is None:
            # Runtime coordinates
            compiler.emit("    ; sprite.draw() with runtime coordinates - TODO")
        else:
            # Compile-time coordinates
            compiler.emit(f"    ; Draw sprite at ({x}, {y})")
            compiler.emit("    ; TODO: implement sprite drawing")
    else:
        raise CompileError("sprite.draw() requires CE target")


def _emit_draw_scale(compiler, node: ast.Call) -> None:
    """Draw a sprite with scaling."""
    if len(node.args) not in (4, 5, 6) or node.keywords:
        raise CompileError("draw_scale() takes sprite, x, y, scale_x, and optional scale_y")
    
    if compiler.target == "ce":
        compiler.emit("    ; sprite.draw_scale() - TODO: implement")
    else:
        raise CompileError("sprite.draw_scale() requires CE target")


def _emit_draw_rotate(compiler, node: ast.Call) -> None:
    """Draw a sprite with rotation."""
    if len(node.args) not in (3, 4) or node.keywords:
        raise CompileError("draw_rotate() takes sprite, x, y, and optional angle")
    
    if compiler.target == "ce":
        compiler.emit("    ; sprite.draw_rotate() - TODO: implement")
    else:
        raise CompileError("sprite.draw_rotate() requires CE target")


def _emit_dimensions(compiler, node: ast.Call) -> None:
    """Get sprite dimensions."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("dimensions() takes sprite")
    
    # For now, return dummy values
    if compiler.target == "ce":
        compiler.emit("    ld hl,16")  # width
        compiler.emit("    push hl")
        compiler.emit("    ld hl,16")  # height
    else:
        raise CompileError("sprite.dimensions() requires CE target")


def _emit_get_pixel(compiler, node: ast.Call) -> None:
    """Get pixel color from sprite."""
    if len(node.args) != 3 or node.keywords:
        raise CompileError("get_pixel() takes sprite, x, y")
    
    if compiler.target == "ce":
        compiler.emit("    ; sprite.get_pixel() - TODO: implement")
    else:
        raise CompileError("sprite.get_pixel() requires CE target")


def _emit_set_pixel(compiler, node: ast.Call) -> None:
    """Set pixel color in sprite."""
    if len(node.args) != 4 or node.keywords:
        raise CompileError("set_pixel() takes sprite, x, y, color")
    
    if compiler.target == "ce":
        compiler.emit("    ; sprite.set_pixel() - TODO: implement")
    else:
        raise CompileError("sprite.set_pixel() requires CE target")


def emit_call(compiler, node: ast.Call) -> None:
    """Emit a sprite library call."""
    if not isinstance(node.func, ast.Attribute):
        raise CompileError("sprite calls must use a sprite library name")
    
    method = node.func.attr
    
    if method == "load":
        _emit_load(compiler, node)
    elif method == "draw":
        _emit_draw(compiler, node)
    elif method == "draw_scale":
        _emit_draw_scale(compiler, node)
    elif method == "draw_rotate":
        _emit_draw_rotate(compiler, node)
    elif method == "dimensions":
        _emit_dimensions(compiler, node)
    elif method == "get_pixel":
        _emit_get_pixel(compiler, node)
    elif method == "set_pixel":
        _emit_set_pixel(compiler, node)
    else:
        supported = ", ".join(f"sprite.{name}()" for name in sorted(ASSEMBLY_API))
        raise CompileError(f"sprite library supports {supported}")
