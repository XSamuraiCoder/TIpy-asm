"""Font library type stubs for TIpy calculator programs.

These stubs describe the font library API for editor completion and type
checking. They do not provide desktop Python runtime implementations.
"""

from typing import Literal

# Color constants (RGB565)
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

class Font: ...

def load(name: str) -> Font: ...
def draw_char(font: Font, char: str, x: int, y: int, color: int = ...) -> None: ...
def draw_text(font: Font, text: str, x: int, y: int, color: int = ...) -> None: ...
def char_width(font: Font, char: str) -> int: ...
def string_width(font: Font, text: str) -> int: ...
def height(font: Font) -> int: ...
def baseline(font: Font) -> int: ...
