"""Color library type stubs for TIpy calculator programs.

These stubs describe the color library API for editor completion and type
checking. They do not provide desktop Python runtime implementations.
"""

# RGB565 color constants
BLACK: int
WHITE: int
RED: int
GREEN: int
BLUE: int
YELLOW: int
CYAN: int
MAGENTA: int
ORANGE: int
PURPLE: int
GRAY: int
LIGHT_GRAY: int
DARK_GRAY: int
PALE_YELLOW: int
PALE_PINK: int
PALE_MINT: int
PEACH: int
MINT: int

# Monochrome constants
MONO_BLACK: int
MONO_WHITE: int

def from_rgb(r: int, g: int, b: int) -> int: ...
def to_grayscale(rgb565: int) -> int: ...
def to_mono(rgb565: int) -> int: ...
def from_mono(mono: int) -> int: ...
def is_valid(value: int) -> bool: ...
def invert(rgb565: int) -> int: ...
def blend(color1: int, color2: int, factor: float = 0.5) -> int: ...
