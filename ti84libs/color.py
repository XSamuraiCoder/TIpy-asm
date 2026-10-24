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
        0 (black) or 1 (white)
    """
    rgb = to_rgb(rgb565)
    return rgb.to_mono(threshold)


def from_mono(mono: int) -> int:
    """Convert monochrome color to RGB565.
    
    Args:
        mono: 0 (black) or 1 (white)
        
    Returns:
        RGB565 color (BLACK or WHITE)
    """
    return BLACK if mono == 0 else WHITE


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


# Public API for the assembly backend
ASSEMBLY_API = {
    "from_rgb",
    "to_rgb",
    "to_grayscale",
    "to_mono",
    "from_mono",
    "invert",
    "blend",
    "is_valid",
}


def _emit_from_rgb(compiler, node: ast.Call) -> None:
    """Emit from_rgb color conversion."""
    if len(node.args) != 3 or node.keywords:
        raise CompileError("color.from_rgb() takes r, g, b (0-255)")
    
    r = compiler.constant_integer(node.args[0])
    g = compiler.constant_integer(node.args[1])
    b = compiler.constant_integer(node.args[2])
    
    if r is None or g is None or b is None:
        raise CompileError("color.from_rgb() requires constant values")
    
    if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
        raise CompileError("color.from_rgb() values must be 0-255")
    
    # Convert to RGB565
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    rgb565 = (r5 << 11) | (g6 << 5) | b5
    
    if compiler.target == "classic":
        # For classic, convert to monochrome
        rgb = RGB(r, g, b)
        mono = rgb.to_mono()
        compiler.emit(f"    ld hl,{0 if mono else 1}")
    else:
        compiler.emit(f"    ld hl,{rgb565}")


def _emit_to_rgb(compiler, node: ast.Call) -> None:
    """Emit to_rgb color conversion."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("color.to_rgb() takes one RGB565 color")
    
    # This returns an RGB object, not a simple value
    # For now, we'll just return the color value
    compiler.expression(node.args[0])


def _emit_to_grayscale(compiler, node: ast.Call) -> None:
    """Emit to_grayscale color conversion."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("color.to_grayscale() takes one RGB565 color")
    
    # Convert to grayscale
    color_val = compiler.constant_integer(node.args[0])
    if color_val is not None:
        gray = to_grayscale(color_val)
        compiler.emit(f"    ld hl,{gray}")
    else:
        # Runtime conversion
        compiler.emit("    ; color.to_grayscale() - TODO: runtime conversion")


def _emit_to_mono(compiler, node: ast.Call) -> None:
    """Emit to_mono color conversion."""
    if len(node.args) not in (1, 2) or node.keywords:
        raise CompileError("color.to_mono() takes RGB565 color and optional threshold")
    
    color_val = compiler.constant_integer(node.args[0])
    threshold = compiler.constant_integer(node.args[1]) if len(node.args) == 2 else 128
    
    if color_val is not None and threshold is not None:
        mono = to_mono(color_val, threshold)
        compiler.emit(f"    ld hl,{0 if mono else 1}")
    else:
        # Runtime conversion
        compiler.emit("    ; color.to_mono() - TODO: runtime conversion")


def _emit_from_mono(compiler, node: ast.Call) -> None:
    """Emit from_mono color conversion."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("color.from_mono() takes 0 or 1")
    
    mono = compiler.constant_integer(node.args[0])
    if mono is not None:
        rgb565 = from_mono(mono)
        compiler.emit(f"    ld hl,{rgb565}")
    else:
        # Runtime conversion
        compiler.emit("    ; color.from_mono() - TODO: runtime conversion")


def _emit_invert(compiler, node: ast.Call) -> None:
    """Emit invert color operation."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("color.invert() takes one RGB565 color")
    
    color_val = compiler.constant_integer(node.args[0])
    if color_val is not None:
        inverted = invert(color_val)
        compiler.emit(f"    ld hl,{inverted}")
    else:
        # Runtime inversion
        compiler.emit("    ; color.invert() - TODO: runtime conversion")


def _emit_blend(compiler, node: ast.Call) -> None:
    """Emit blend color operation."""
    if len(node.args) not in (2, 3) or node.keywords:
        raise CompileError("color.blend() takes color1, color2, and optional factor")
    
    # Blending is complex, skip for now
    compiler.emit("    ; color.blend() - TODO: implement blending")


def emit_call(compiler, node: ast.Call) -> None:
    """Emit a color library call."""
    if not isinstance(node.func, ast.Attribute):
        raise CompileError("color calls must use a color library name")
    
    method = node.func.attr
    
    if method == "from_rgb":
        _emit_from_rgb(compiler, node)
    elif method == "to_rgb":
        _emit_to_rgb(compiler, node)
    elif method == "to_grayscale":
        _emit_to_grayscale(compiler, node)
    elif method == "to_mono":
        _emit_to_mono(compiler, node)
    elif method == "from_mono":
        _emit_from_mono(compiler, node)
    elif method == "invert":
        _emit_invert(compiler, node)
    elif method == "blend":
        _emit_blend(compiler, node)
    elif method == "is_valid":
        compiler.emit("    ; color.is_valid() - TODO: implement")
    else:
        supported = ", ".join(f"color.{name}()" for name in sorted(ASSEMBLY_API))
        raise CompileError(f"color library supports {supported}")
