"""Compile-time drawing library for monochrome TI-84 and RGB565 CE screens.

CE colors are 16-bit RGB565 values. The classic target remains monochrome and
maps color 0 to white and any nonzero color to black.
"""

import ast

from ti84asm.errors import CompileError
from .util import literal_integer


# RGB565 palette constants, usable as graphics.COLOR attributes in source.
COLORS = {
    "BLACK": 0x0000, "WHITE": 0xFFFF, "RED": 0xF800, "GREEN": 0x07E0,
    "BLUE": 0x001F, "YELLOW": 0xFFE0, "CYAN": 0x07FF, "MAGENTA": 0xF81F,
    "ORANGE": 0xFD70, "PINK": 0xFC75, "PURPLE": 0x801F, "MINT": 0xD7BC,
    "PEACH": 0xFDF0, "PALE_YELLOW": 0xFEF0, "PALE_PINK": 0xFCB6,
    "PALE_MINT": 0xD7BC, "GRAY": 0x8410,
}


def emit_attribute(compiler, node: ast.Attribute) -> None:
    if not isinstance(node.value, ast.Name) or compiler.modules.get(node.value.id) != "ti84.graphics":
        raise CompileError("unsupported graphics constant")
    value = COLORS.get(node.attr.upper())
    if value is None:
        raise CompileError(f"unknown graphics color: {node.attr}")
    if compiler.target == "classic":
        value = 0 if value == 0xFFFF else 1
    compiler.emit(f"    ld hl,{value}")


def _emit_pixel(compiler, x: int, y: int, color: int) -> None:
    if compiler.target == "classic":
        compiler.emit(f"    ld bc,{x * 256 + y}")
        compiler.emit(f"    ld d,{color}")
        compiler.emit("    bcall(_IPoint)")
    else:
        address = 0xD40000 + (y * 320 + x) * 2
        compiler.emit(f"    ld hl,${address:06X}")
        ce_color = color & 0xFFFF
        compiler.emit(f"    ld de,${ce_color:04X}")
        compiler.emit("    ld (hl),e")
        compiler.emit("    inc hl")
        compiler.emit("    ld (hl),d")


def _emit_fill_rect(compiler, x: int, y: int, width: int, height: int, color: int) -> None:
    screen_width, screen_height = (96, 64) if compiler.target == "classic" else (320, 240)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(screen_width, x + width), min(screen_height, y + height)
    if x0 >= x1 or y0 >= y1:
        return
    if compiler.target == "classic":
        for row in range(y0, y1):
            _emit_line(compiler, x0, row, x1 - 1, row, 0 if color == 0 else 1)
        return
    for row in range(y0, y1):
        for chunk_x in range(x0, x1, 255):
            count = min(255, x1 - chunk_x)
            address = 0xD40000 + (row * screen_width + chunk_x) * 2
            loop = compiler.label("gfx_fill_x")
            compiler.emit(f"    ld hl,${address:06X}")
            compiler.emit(f"    ld de,${color & 0xFFFF:04X}")
            compiler.emit(f"    ld b,{count}")
            compiler.emit(loop + ":")
            compiler.emit("    ld (hl),e")
            compiler.emit("    inc hl")
            compiler.emit("    ld (hl),d")
            compiler.emit("    inc hl")
            compiler.emit(f"    djnz {loop}")


def _emit_flush(compiler) -> None:
    """Copy the classic graph buffer once after a complete drawing operation."""
    if compiler.target == "classic":
        compiler.emit("    bcall(_GrBufCpy)")


def _color(compiler, node: ast.expr, purpose: str, default: int = 1) -> int:
    if node is None:
        return default
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if compiler.modules.get(node.value.id) == "ti84.graphics" and node.attr.upper() in COLORS:
            value = COLORS[node.attr.upper()]
            return (0 if value == 0xFFFF else 1) if compiler.target == "classic" else value
    value = literal_integer(node, purpose, allow_unsigned=compiler.target == "ce")
    if compiler.target == "classic":
        return 0 if value == 0 else 1
    return value


def _default_color(compiler) -> int:
    # Classic TI graphing calculators use 1 for black; CE uses RGB565 black.
    return 1 if compiler.target == "classic" else COLORS["BLACK"]


def _emit_filled_triangle(compiler, points: tuple[tuple[int, int], ...], color: int) -> None:
    """Rasterize a literal triangle into horizontal spans at compile time."""
    (x0, y0), (x1, y1), (x2, y2) = points
    lo_y, hi_y = min(y0, y1, y2), max(y0, y1, y2)
    height = 64 if compiler.target == "classic" else 240
    width = 96 if compiler.target == "classic" else 320
    edges = ((x0, y0, x1, y1), (x1, y1, x2, y2), (x2, y2, x0, y0))
    for scan_y in range(max(0, lo_y), min(height - 1, hi_y) + 1):
        intersections: list[int] = []
        for ax, ay, bx, by in edges:
            if ay == by:
                if scan_y == ay:
                    intersections.extend((ax, bx))
            elif min(ay, by) <= scan_y <= max(ay, by):
                intersections.append(ax + (scan_y - ay) * (bx - ax) // (by - ay))
        if intersections:
            left = max(0, min(intersections))
            right = min(width - 1, max(intersections))
            if left <= right:
                _emit_fill_rect(compiler, left, scan_y, right - left + 1, 1, color)


def _emit_line(compiler, x1: int, y1: int, x2: int, y2: int, color: int) -> None:
    dx, sx = abs(x2 - x1), 1 if x1 < x2 else -1
    dy, sy = -abs(y2 - y1), 1 if y1 < y2 else -1
    error = dx + dy
    while True:
        _emit_pixel(compiler, x1, y1, color)
        if x1 == x2 and y1 == y2:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x1 += sx
        if twice <= dx:
            error += dx
            y1 += sy


def emit_call(compiler, node: ast.Call) -> None:
    if not isinstance(node.func, ast.Attribute):
        raise CompileError("graphics calls must use a graphics library name")
    method = node.func.attr

    if method == "clear" and not node.args and not node.keywords:
        if compiler.target == "classic":
            compiler.emit("    bcall(_GrBufClr)")
            compiler.emit("    bcall(_GrBufCpy)")
        else:
            compiler.emit("    call ti.RunIndicOff")
            compiler.emit("    call ti.boot.ClearVRAM")
            compiler.emit("    ld a,ti.lcdBpp16")
            compiler.emit("    ld (ti.mpLcdCtrl),a")
    elif method == "wait_key" and not node.args and not node.keywords:
        released = compiler.label("wait_release")
        wait = compiler.label("wait_key")
        if compiler.target == "classic":
            compiler.emit(released + ":")
            compiler.emit("    bcall(_GetCSC)")
            compiler.emit("    or a")
            compiler.emit(f"    jr nz,{released}")
            compiler.emit(wait + ":")
            compiler.emit("    bcall(_GetCSC)")
            compiler.emit("    or a")
            compiler.emit(f"    jr z,{wait}")
        else:
            compiler.emit(released + ":")
            compiler.emit("    call ti.GetCSC")
            compiler.emit("    or a,a")
            compiler.emit(f"    jr nz,{released}")
            compiler.emit(wait + ":")
            compiler.emit("    call ti.GetCSC")
            compiler.emit("    or a,a")
            compiler.emit(f"    jr z,{wait}")
    elif method == "pixel":
        if node.keywords and (len(node.keywords) != 1 or node.keywords[0].arg != "color"):
            raise CompileError("pixel() only accepts the color keyword")
        if not 2 <= len(node.args) <= 3:
            raise CompileError("pixel() takes x, y, and optional color")
        if node.keywords and len(node.args) == 3:
            raise CompileError("pixel color may be positional or keyword, not both")
        args = list(node.args)
        color = node.keywords[0].value if node.keywords else (args.pop() if len(args) == 3 else ast.Constant(value=1))
        x, y = (literal_integer(arg, "pixel coordinates") for arg in args[:2])
        color_value = _color(compiler, color, "pixel color", _default_color(compiler))
        width, height = (96, 64) if compiler.target == "classic" else (320, 240)
        if not (0 <= x < width and 0 <= y < height):
            raise CompileError(f"{compiler.target} pixel coordinates must fit {width}x{height} screen")
        _emit_pixel(compiler, x, y, color_value)
        _emit_flush(compiler)
    elif method == "line":
        if node.keywords or len(node.args) not in (4, 5):
            raise CompileError("line() takes x1, y1, x2, y2, and optional color")
        x1, y1, x2, y2 = (literal_integer(arg, "line coordinates") for arg in node.args[:4])
        color = _color(compiler, node.args[4], "line color", _default_color(compiler)) if len(node.args) == 5 else _default_color(compiler)
        width, height = (96, 64) if compiler.target == "classic" else (320, 240)
        if any(not (0 <= x < width and 0 <= y < height) for x, y in ((x1, y1), (x2, y2))):
            raise CompileError(f"{compiler.target} line coordinates must fit {width}x{height} screen")
        _emit_line(compiler, x1, y1, x2, y2, color)
        _emit_flush(compiler)
    elif method == "rect":
        if node.keywords or len(node.args) not in (4, 5):
            raise CompileError("rect() takes x, y, width, height, and optional color")
        x, y, rect_width, rect_height = (literal_integer(arg, "rectangle values") for arg in node.args[:4])
        color = _color(compiler, node.args[4], "rectangle color", _default_color(compiler)) if len(node.args) == 5 else _default_color(compiler)
        screen_width, screen_height = (96, 64) if compiler.target == "classic" else (320, 240)
        if rect_width < 1 or rect_height < 1 or x + rect_width >= screen_width or y + rect_height >= screen_height:
            raise CompileError(f"rectangle must fit within the {screen_width}x{screen_height} screen")
        _emit_line(compiler, x, y, x + rect_width, y, color)
        _emit_line(compiler, x + rect_width, y, x + rect_width, y + rect_height, color)
        _emit_line(compiler, x + rect_width, y + rect_height, x, y + rect_height, color)
        _emit_line(compiler, x, y + rect_height, x, y, color)
        _emit_flush(compiler)
    elif method == "circle":
        if node.keywords or len(node.args) not in (3, 4):
            raise CompileError("circle() takes center_x, center_y, radius, and optional color")
        cx, cy, radius = (literal_integer(arg, "circle values") for arg in node.args[:3])
        color = _color(compiler, node.args[3], "circle color", _default_color(compiler)) if len(node.args) == 4 else _default_color(compiler)
        screen_width, screen_height = (96, 64) if compiler.target == "classic" else (320, 240)
        if radius < 1 or cx - radius < 0 or cy - radius < 0 or cx + radius >= screen_width or cy + radius >= screen_height:
            raise CompileError(f"circle must fit within the {screen_width}x{screen_height} screen")
        x, y, error = radius, 0, 1 - radius
        while x >= y:
            points = ((cx + x, cy + y), (cx + y, cy + x), (cx - y, cy + x), (cx - x, cy + y),
                      (cx - x, cy - y), (cx - y, cy - x), (cx + y, cy - x), (cx + x, cy - y))
            for px, py in points:
                _emit_pixel(compiler, px, py, color)
            y += 1
            if error < 0:
                error += 2 * y + 1
            else:
                x -= 1
                error += 2 * (y - x) + 1
        _emit_flush(compiler)
    elif method == "fill_rect":
        if node.keywords or len(node.args) not in (4, 5):
            raise CompileError("fill_rect() takes x, y, width, height, and optional color")
        x, y, rect_width, rect_height = (literal_integer(arg, "filled rectangle values") for arg in node.args[:4])
        color = _color(compiler, node.args[4], "filled rectangle color", _default_color(compiler)) if len(node.args) == 5 else _default_color(compiler)
        if rect_width < 1 or rect_height < 1:
            raise CompileError("filled rectangle width and height must be positive")
        _emit_fill_rect(compiler, x, y, rect_width, rect_height, color)
        _emit_flush(compiler)
    elif method == "triangle":
        if node.keywords or len(node.args) not in (6, 7):
            raise CompileError("triangle() takes three x/y points and optional color")
        values = tuple(literal_integer(arg, "triangle coordinates") for arg in node.args[:6])
        color = _color(compiler, node.args[6], "triangle color", _default_color(compiler)) if len(node.args) == 7 else _default_color(compiler)
        points = ((values[0], values[1]), (values[2], values[3]), (values[4], values[5]))
        _emit_filled_triangle(compiler, points, color)
        _emit_flush(compiler)
    else:
        raise CompileError("graphics supports clear(), pixel(), line(), rect(), fill_rect(), triangle(), circle(), and wait_key()")
