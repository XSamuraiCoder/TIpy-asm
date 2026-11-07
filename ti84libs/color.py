"""Color utilities for TIpy-asm.

Provides color handling and conversion between different color formats,
making it easy to work with both monochrome (classic TI-84) and color
(CE) graphics interchangeably.

Usage:
    from ti84 import color
    
    # RGB565 color constants
    red = color.RED
    green = color.GREEN
    
    # Convert between formats
    rgb565 = color.from_rgb(255, 0, 0)  # Pure red
    rgb = color.to_rgb(rgb565)        # (255, 0, 0)
    
    # Monochrome conversion
    mono = color.to_mono(rgb565)  # 0 or 1
    rgb565_from_mono = color.from_mono(mono)
    
    # Grayscale conversion
    gray = color.to_grayscale(rgb565)
    
    # Check if color is valid
    if color.is_valid_rgb565(rgb565):
        print("Valid color")
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ti84asm.errors import CompileError


# RGB565 color constants (16-bit: 5 red, 6 green, 5 blue)
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
LIGHT_GRAY = 0xAD55
DARK_GRAY = 0x4208
PALE_YELLOW = 0xFEF0
PALE_PINK = 0xFCB6
PALE_MINT = 0xD7BC
PEACH = 0xFDF0
MINT = 0xD7BC


# Monochrome color constants (for classic TI-84)
MONO_BLACK = 0
MONO_WHITE = 1


@dataclass
class RGB:
    """RGB color representation."""
    r: int
    g: int
    b: int
    
    def to_rgb565(self) -> int:
        """Convert RGB to RGB565 format."""
        r5 = (self.r >> 3) & 0x1F
        g6 = (self.g >> 2) & 0x3F
        b5 = (self.b >> 3) & 0x1F
        return (r5 << 11) | (g6 << 5) | b5
    
    def to_grayscale(self) -> "RGB":
        """Convert RGB to grayscale using luminance formula."""
        # Luminance formula: Y = 0.299*R + 0.587*G + 0.114*B
        y = int(0.299 * self.r + 0.587 * self.g + 0.114 * self.b)
        return RGB(y, y, y)
    
    def to_mono(self, threshold: int = 128) -> int:
        """Convert RGB to monochrome (0 or 1) based on luminance threshold."""
        y = int(0.299 * self.r + 0.587 * self.g + 0.114 * self.b)
        return 0 if y >= threshold else 1


def from_rgb(r: int, g: int, b: int) -> int:
    """Create RGB565 color from RGB components.
    
    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)
        
    Returns:
        RGB565 color (0-65535)
    """
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    return (r5 << 11) | (g6 << 5) | b5


def to_rgb(rgb565: int) -> RGB:
    """Convert RGB565 color to RGB components.
    
    Args:
        rgb565: RGB565 color (0-65535)
        
    Returns:
        RGB tuple with components (0-255)
    """
    r5 = (rgb565 >> 11) & 0x1F
    g6 = (rgb565 >> 5) & 0x3F
    b5 = rgb565 & 0x1F
    
    # Scale back to 8-bit
    r8 = (r5 * 255 + 15) // 31
    g8 = (g6 * 255 + 31) // 63
    b8 = (b5 * 255 + 15) // 31
    
    return RGB(r8, g8, b8)


def to_grayscale(rgb565: int) -> int:
    """Convert RGB565 color to grayscale RGB565.
    
    Args:
        rgb565: RGB565 color
        
    Returns:
        Grayscale RGB565 color
    """
    rgb = to_rgb(rgb565)
    gray_rgb = rgb.to_grayscale()
    return gray_rgb.to_rgb565()


def to_mono(rgb565: int, threshold: int = 128) -> int:
    """Convert RGB565 color to monochrome (0 or 1).
    
    Args:
        rgb565: RGB565 color
        threshold: Luminance threshold (0-255), default 128
        
    Returns:
        0 (white, a bright color) or 1 (black, a dark color)
    """
    rgb = to_rgb(rgb565)
    return rgb.to_mono(threshold)


def from_mono(mono: int) -> int:
    """Convert monochrome color to RGB565.
    
    Args:
        mono: 0 (white) or nonzero (black), the classic screen's convention
        
    Returns:
        RGB565 color (WHITE or BLACK)
    """
    return WHITE if mono == 0 else BLACK


def is_valid_rgb565(value: int) -> bool:
    """Check if a value is a valid RGB565 color.
    
    Args:
        value: Value to check
        
    Returns:
        True if value is a valid RGB565 color (0-65535)
    """
    return 0 <= value <= 0xFFFF


def invert(rgb565: int) -> int:
    """Invert an RGB565 color.
    
    Args:
        rgb565: RGB565 color
        
    Returns:
        Inverted RGB565 color
    """
    r5 = (rgb565 >> 11) & 0x1F
    g6 = (rgb565 >> 5) & 0x3F
    b5 = rgb565 & 0x1F
    return ((0x1F - r5) << 11) | ((0x3F - g6) << 5) | (0x1F - b5)


def blend(color1: int, color2: int, factor: float = 0.5) -> int:
    """Blend two RGB565 colors.
    
    Args:
        color1: First RGB565 color
        color2: Second RGB565 color
        factor: Blend factor (0.0 to 1.0)
        
    Returns:
        Blended RGB565 color
    """
    rgb1 = to_rgb(color1)
    rgb2 = to_rgb(color2)
    
    r = int(rgb1.r + (rgb2.r - rgb1.r) * factor)
    g = int(rgb1.g + (rgb2.g - rgb1.g) * factor)
    b = int(rgb1.b + (rgb2.b - rgb1.b) * factor)
    
    return from_rgb(r, g, b)


CONSTANTS = {name: value for name, value in list(globals().items())
             if name.isupper() and isinstance(value, int) and not name.startswith("MONO_")}


def constant(compiler, name: str) -> int | None:
    """Return a color constant in the target's own color format."""
    value = CONSTANTS.get(name.upper())
    if value is None:
        return None
    if compiler.target == "classic":
        return 0 if value == WHITE else 1
    return value


def _channels(compiler, node: ast.Call) -> list[int] | None:
    values = [compiler.constant_integer(argument) for argument in node.args]
    return None if any(value is None for value in values) else values


def constant_call(compiler, node: ast.Call) -> int | None:
    """Fold a color call whose arguments are all constants; None if it must run."""
    method = node.func.attr
    if node.keywords:
        return None
    if method == "blend":
        return _constant_blend(compiler, node)
    values = _channels(compiler, node)
    if values is None:
        return None
    classic = compiler.target == "classic"
    if method == "from_rgb" and len(values) == 3:
        if not all(0 <= value <= 255 for value in values):
            raise CompileError("color.from_rgb() values must be 0-255")
        return RGB(*values).to_mono() if classic else from_rgb(*values)
    if len(values) != 1:
        return None
    value = values[0]
    if method == "to_mono":
        return (0 if value == 0 else 1) if classic else to_mono(value)
    if method == "from_mono":
        return (0 if value == 0 else 1) if classic else from_mono(value)
    if method == "is_valid":
        return 1 if classic or is_valid_rgb565(value) else 0
    if classic:
        return None
    if method == "invert":
        return invert(value)
    if method == "to_grayscale":
        return to_grayscale(value)
    return None


def _constant_blend(compiler, node: ast.Call) -> int | None:
    if compiler.target == "classic":
        return None
    if len(node.args) not in (2, 3):
        raise CompileError("color.blend() takes color1, color2, and an optional factor from 0.0 to 1.0")
    first, second = compiler.constant_integer(node.args[0]), compiler.constant_integer(node.args[1])
    factor = 0.5
    if len(node.args) == 3:
        literal = node.args[2]
        if not isinstance(literal, ast.Constant) or not isinstance(literal.value, (int, float)):
            raise CompileError("color.blend() factor must be a number literal")
        factor = literal.value
    if first is None or second is None:
        raise CompileError("color.blend() needs constant colors")
    return blend(first, second, factor)


_RUNTIME = {"from_rgb": ("_tipy_from_rgb", 3), "to_mono": ("_tipy_to_mono", 1), "from_mono": ("_tipy_from_mono", 1),
            "invert": ("_tipy_invert", 1), "to_grayscale": ("_tipy_grayscale", 1), "is_valid": ("_tipy_is_valid", 1)}


def emit_call(compiler, node: ast.Call) -> None:
    """Emit a color call: folded when constant, otherwise a runtime function."""
    method = node.func.attr
    if node.keywords:
        raise CompileError(f"color.{method}() uses positional arguments")
    folded = constant_call(compiler, node)
    if folded is not None:
        compiler.emit(f"    ld hl,{compiler.integer_literal(folded)}")
        return
    function, arity = _RUNTIME[method]
    if len(node.args) != arity:
        raise CompileError(f"color.{method}() takes {arity} argument(s), got {len(node.args)}")
    classic = compiler.target == "classic"
    if classic and method == "from_rgb":
        function = "_tipy_from_rgb_mono"
    elif classic and method in ("to_mono", "from_mono"):
        function = "_tipy_bool"
    elif classic and method == "is_valid":
        compiler.emit("    ld hl,1")
        return
    compiler.call_function(function, list(node.args))
