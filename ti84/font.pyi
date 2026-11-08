"""FontLibC font packs (built by convfont or a font asset) on the CE, plus color constants."""

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

def load(name: str, index: int = 0) -> int: ...
def count(name: str) -> int: ...
def height(font: int) -> int: ...
def width(font: int, code: int) -> int: ...
def char(font: int, code: int, x: int, y: int, color: int = ...) -> int: ...
