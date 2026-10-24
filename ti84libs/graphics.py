"""Compile-time drawing library for monochrome TI-84 and RGB565 CE screens.

CE colors are 16-bit RGB565 values. The classic target remains monochrome and
maps color 0 to white and any nonzero color to black.
"""

import ast

from ti84asm.errors import CompileError
from .util import literal_integer


# Public calls handled by the standalone assembly backend. Keep this in sync
# with the dispatch below and the shared IntelliSense stub.
ASSEMBLY_API = {
    "begin", "end", "clear", "wait_key", "delay", "pixel", "sprite", "text",
    "line", "rect", "circle", "fill_rect", "triangle",
}


# RGB565 palette constants, usable as graphics.COLOR attributes in source.
COLORS = {
    "BLACK": 0x0000, "WHITE": 0xFFFF, "RED": 0xF800, "GREEN": 0x07E0,
    "BLUE": 0x001F, "YELLOW": 0xFFE0, "CYAN": 0x07FF, "MAGENTA": 0xF81F,
    "ORANGE": 0xFD70, "PINK": 0xFC75, "PURPLE": 0x801F, "MINT": 0xD7BC,
    "PEACH": 0xFDF0, "PALE_YELLOW": 0xFEF0, "PALE_PINK": 0xFCB6,
    "PALE_MINT": 0xD7BC, "GRAY": 0x8410,
}

# Compact 5x7 bitmap font used when graphics.text() is compiled to assembly.
# Lowercase input is rendered in uppercase so the glyph table stays small.
FONT_5X7 = {
    " ": ("00000",) * 7,
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00110", "00100"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "'": ("00100", "00100", "00010", "00000", "00000", "00000", "00000"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
}


def emit_attribute(compiler, node: ast.Attribute) -> None:
    if not isinstance(node.value, ast.Name) or compiler.modules.get(node.value.id) != "ti84.graphics":
        raise CompileError("unsupported graphics constant")
    if node.attr in ("width", "height"):
        dimensions = ((96, 64) if compiler.target == "classic" else (320, 240))
        value = dimensions[0 if node.attr == "width" else 1]
        compiler.emit(f"    ld hl,{value}")
        return
    value = COLORS.get(node.attr.upper())
    if value is None:
        raise CompileError(f"unknown graphics constant: {node.attr}")
    if compiler.target == "classic":
        value = 0 if value == 0xFFFF else 1
    compiler.emit(f"    ld hl,{value}")


def _emit_sprite(compiler, node: ast.Call) -> None:
    if node.keywords or len(node.args) != 3:
        raise CompileError("sprite() takes a tuple of pixel rows, x, and y")
    rows_node = node.args[0]
    if isinstance(rows_node, ast.Name):
        rows_node = compiler.constants.get(rows_node.id)
        if rows_node is None:
            raise CompileError(f"unknown sprite constant: {node.args[0].id}")
    if not isinstance(rows_node, (ast.Tuple, ast.List)) or not rows_node.elts:
        raise CompileError("sprite pixels must be a nonempty tuple or list of rows")
    rows: list[list[int | None]] = []
    width: int | None = None
    for row_node in rows_node.elts:
        if not isinstance(row_node, (ast.Tuple, ast.List)) or not row_node.elts:
            raise CompileError("each sprite row must be a nonempty tuple or list")
        if width is None:
            width = len(row_node.elts)
        elif len(row_node.elts) != width:
            raise CompileError("all sprite rows must have the same width")
        row: list[int | None] = []
        for pixel in row_node.elts:
            if isinstance(pixel, ast.Constant) and pixel.value is None:
                row.append(None)
            elif (isinstance(pixel, ast.Constant) and isinstance(pixel.value, int)
                  and not isinstance(pixel.value, bool) and 0 <= pixel.value <= 0xFFFF):
                row.append(pixel.value)
            else:
                raise CompileError("sprite pixels must be RGB565 integers or None for transparent")
        rows.append(row)

    x = compiler.constant_integer(node.args[1])
    y = compiler.constant_integer(node.args[2])
    screen_width, screen_height = (96, 64) if compiler.target == "classic" else (320, 240)
    if compiler.target == "ce":
        _emit_dynamic_sprite(compiler, rows, width or 0, len(rows), node.args[1], node.args[2],
                             screen_width, screen_height)
        return
    if x is None or y is None:
        _emit_dynamic_sprite(compiler, rows, width or 0, len(rows), node.args[1], node.args[2],
                             screen_width, screen_height)
        return
    for sy, row in enumerate(rows):
        py = y + sy
        if not 0 <= py < screen_height:
            continue
        for sx, color in enumerate(row):
            px = x + sx
            if color is None or not 0 <= px < screen_width:
                continue
            if compiler.target == "classic":
                red, green, blue = (color >> 11) & 31, (color >> 5) & 63, color & 31
                # Reduce RGB565 to monochrome with a simple luminance threshold.
                luminance = red * 299 + green * 587 + blue * 114
                color = 0 if luminance >= 31 * 1000 else 1
            _emit_pixel(compiler, px, py, color)
    _emit_flush(compiler)


def _emit_dynamic_sprite(compiler, rows: list[list[int | None]], width: int, height: int,
                         x_node: ast.expr, y_node: ast.expr,
                         screen_width: int, screen_height: int) -> None:
    """Draw a literal sprite at runtime coordinates, clipping its edges."""
    if width > screen_width or height > screen_height:
        raise CompileError(
            f"runtime sprite dimensions must fit within {screen_width}x{screen_height}"
        )
    x_label = compiler.label("sprite_x")
    y_label = compiler.label("sprite_y")
    if compiler.target == "classic":
        compiler.data.extend((f"{x_label}: .dw 0", f"{y_label}: .dw 0"))
    else:
        compiler.data.extend((f"{x_label}: db 0,0,0", f"{y_label}: db 0,0,0"))

    for expression, label in ((x_node, x_label), (y_node, y_label)):
        compiler.expression(expression)
        compiler.emit(f"    ld ({label}),hl")

    if compiler.target == "classic":
        # Check each opaque pixel in top-left coordinates. This permits a
        # sprite to enter from any edge while keeping wrapped coordinates
        # away from the ROM pixel routine.
        compiler.emit("    res plotLoc,(iy+plotFlags)")
        compiler.emit("    set fullScrnDraw,(iy+apiFlg4)")
        for sy, row in enumerate(rows):
            for sx, color in enumerate(row):
                if color is None:
                    continue
                red, green, blue = (color >> 11) & 31, (color >> 5) & 63, color & 31
                luminance = red * 299 + green * 587 + blue * 114
                mono = 0 if luminance >= 31 * 1000 else 1
                pixel_skip = compiler.label("sprite_pixel_clipped")
                x_ok = compiler.label("sprite_pixel_x_ok")
                y_ok = compiler.label("sprite_pixel_y_ok")
                compiler.emit(f"    ld hl,({x_label})")
                if sx:
                    compiler.emit(f"    ld de,{sx}")
                    compiler.emit("    add hl,de")
                compiler.emit("    bit 7,h")
                compiler.emit(f"    jp nz,{pixel_skip}")
                compiler.emit("    push hl")
                compiler.emit(f"    ld de,{screen_width - 1}")
                compiler.emit("    or a")
                compiler.emit("    sbc hl,de")
                compiler.emit(f"    jp c,{x_ok}")
                compiler.emit(f"    jp z,{x_ok}")
                compiler.emit("    pop hl")
                compiler.emit(f"    jp {pixel_skip}")
                compiler.emit(x_ok + ":")
                compiler.emit("    pop hl")
                compiler.emit("    ld b,l")
                compiler.emit(f"    ld hl,({y_label})")
                if sy:
                    compiler.emit(f"    ld de,{sy}")
                    compiler.emit("    add hl,de")
                compiler.emit("    bit 7,h")
                compiler.emit(f"    jp nz,{pixel_skip}")
                compiler.emit("    push hl")
                compiler.emit(f"    ld de,{screen_height - 1}")
                compiler.emit("    or a")
                compiler.emit("    sbc hl,de")
                compiler.emit(f"    jp c,{y_ok}")
                compiler.emit(f"    jp z,{y_ok}")
                compiler.emit("    pop hl")
                compiler.emit(f"    jp {pixel_skip}")
                compiler.emit(y_ok + ":")
                compiler.emit("    pop hl")
                compiler.emit(f"    ld de,{screen_height - 1}")
                compiler.emit("    or a")
                compiler.emit("    ex de,hl")
                compiler.emit("    sbc hl,de")
                compiler.emit("    ld c,l")
                compiler.emit(f"    ld d,{mono}")
                compiler.emit("    bcall(_IPoint)")
                compiler.emit(pixel_skip + ":")

    if compiler.target == "ce":
        x_current = compiler.label("sprite_x_current")
        y_current = compiler.label("sprite_y_current")
        pixel_ptr = compiler.label("sprite_ptr")
        compiler.data.extend((f"{x_current}: db 0,0,0", f"{y_current}: db 0,0,0", f"{pixel_ptr}: db 0,0,0"))
        # Store each pixel as alpha + RGB565. A small run-time renderer
        # keeps code size low and clips edge pixels like GraphX.
        sprite_data = compiler.label("sprite_data")
        encoded: list[int] = []
        for row in rows:
            for color in row:
                if color is None:
                    encoded.extend((0, 0, 0))
                else:
                    encoded.extend((1, color & 0xFF, color >> 8))
        compiler.data_bytes(sprite_data, encoded)

        # Convert the pixel origin to VRAM once: base + y*640 + x*2.
        compiler.emit(f"    ld hl,({y_label})")
        for _ in range(7):
            compiler.emit("    add hl,hl")  # y * 128
        compiler.emit("    push hl")
        compiler.emit("    add hl,hl")
        compiler.emit("    add hl,hl")  # y * 512
        compiler.emit("    pop de")       # y * 128
        compiler.emit("    add hl,de")   # y * 640
        compiler.emit("    push hl")
        compiler.emit(f"    ld hl,({x_label})")
        compiler.emit("    add hl,hl")
        compiler.emit("    pop de")
        compiler.emit("    add hl,de")
        compiler.emit("    ld de,$D40000")
        compiler.emit("    add hl,de")
        compiler.emit(f"    ld ({pixel_ptr}),hl")   # HL is reused below; remember the VRAM pointer
        row_stride = screen_width * 2 - width * 2
        compiler.emit(f"    ld ix,{sprite_data}")
        row_loop = compiler.label("sprite_row")
        compiler.emit(f"    ld hl,({y_label})")
        compiler.emit(f"    ld ({y_current}),hl")
        compiler.emit(f"    ld b,{height}")
        compiler.emit(row_loop + ":")
        compiler.emit(f"    ld hl,({x_label})")
        compiler.emit(f"    ld ({x_current}),hl")
        compiler.emit(f"    ld hl,({pixel_ptr})")   # continue at this row's first VRAM pixel
        for chunk_start in range(0, width, 255):
            chunk_width = min(255, width - chunk_start)
            column_loop = compiler.label("sprite_column")
            transparent = compiler.label("sprite_transparent")
            advanced = compiler.label("sprite_advanced")
            clipped = compiler.label("sprite_pixel_clipped")
            compiler.emit(f"    ld c,{chunk_width}")
            compiler.emit(column_loop + ":")
            compiler.emit("    ld a,(ix)")
            compiler.emit("    or a,a")
            compiler.emit(f"    jr z,{transparent}")
            compiler.emit("    push hl")
            compiler.emit(f"    ld hl,({y_current})")
            compiler.emit(f"    ld de,{screen_height}")
            compiler.emit("    or a")
            compiler.emit("    sbc hl,de")
            compiler.emit(f"    jr nc,{clipped}")
            compiler.emit(f"    ld hl,({x_current})")
            compiler.emit(f"    ld de,{screen_width}")
            compiler.emit("    or a")
            compiler.emit("    sbc hl,de")
            compiler.emit(f"    jr nc,{clipped}")
            compiler.emit("    pop hl")
            compiler.emit("    ld e,(ix+1)")
            compiler.emit("    ld d,(ix+2)")
            compiler.emit("    ld (hl),e")
            compiler.emit("    inc hl")
            compiler.emit("    ld (hl),d")
            compiler.emit("    inc hl")
            compiler.emit(f"    jr {advanced}")
            compiler.emit(clipped + ":")
            compiler.emit("    pop hl")
            compiler.emit(f"    jr {transparent}")
            compiler.emit(transparent + ":")
            compiler.emit("    inc hl")
            compiler.emit("    inc hl")
            compiler.emit(advanced + ":")
            compiler.emit("    push hl")
            compiler.emit(f"    ld hl,({x_current})")
            compiler.emit("    inc hl")
            compiler.emit(f"    ld ({x_current}),hl")
            compiler.emit("    pop hl")
            compiler.emit("    inc ix")
            compiler.emit("    inc ix")
            compiler.emit("    inc ix")
            compiler.emit("    dec c")
            compiler.emit(f"    jr nz,{column_loop}")
        if row_stride:
            compiler.emit(f"    ld de,{row_stride}")
            compiler.emit("    add hl,de")
        compiler.emit(f"    ld ({pixel_ptr}),hl")
        compiler.emit("    push hl")
        compiler.emit(f"    ld hl,({y_current})")
        compiler.emit("    inc hl")
        compiler.emit(f"    ld ({y_current}),hl")
        compiler.emit("    pop hl")
        compiler.emit(f"    djnz {row_loop}")
    _emit_flush(compiler)


def _emit_pixel(compiler, x: int, y: int, color: int) -> None:
    if compiler.target == "classic":
        compiler.emit("    res plotLoc,(iy+plotFlags)")
        compiler.emit(f"    ld bc,{x * 256 + 63 - y}")
        compiler.emit("    set fullScrnDraw,(iy+apiFlg4)")
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
        # The ROM rectangle routines use inclusive, top-left-origin pixel
        # coordinates and update both the LCD and graph buffer when plotLoc
        # is clear. This replaces thousands of generated _IPoint calls for
        # large fills with one bounded ROM call.
        upper_left = (y0 << 8) | x0
        lower_right = ((y1 - 1) << 8) | (x1 - 1)
        compiler.emit("    res plotLoc,(iy+plotFlags)")
        compiler.emit(f"    ld hl,{upper_left}")
        compiler.emit(f"    ld de,{lower_right}")
        compiler.emit(f"    bcall({'_FillRect' if color else '_ClearRect'})")
        return
    rect_width = x1 - x0
    row_stride = screen_width * 2 - rect_width * 2
    address = 0xD40000 + (y0 * screen_width + x0) * 2
    row_loop = compiler.label("gfx_fill_y")
    compiler.emit(f"    ld hl,${address:06X}")
    compiler.emit(f"    ld de,${color & 0xFFFF:04X}")
    compiler.emit(f"    ld b,{y1 - y0}")
    compiler.emit(row_loop + ":")
    for chunk_x in range(x0, x1, 255):
        count = min(255, x1 - chunk_x)
        pixel_loop = compiler.label("gfx_fill_x")
        compiler.emit(f"    ld c,{count}")
        compiler.emit(pixel_loop + ":")
        compiler.emit("    ld (hl),e")
        compiler.emit("    inc hl")
        compiler.emit("    ld (hl),d")
        compiler.emit("    inc hl")
        compiler.emit("    dec c")
        compiler.emit(f"    jr nz,{pixel_loop}")
    if row_stride:
        # Preserve the RGB565 value in DE while advancing HL to the next row.
        compiler.emit("    push de")
        compiler.emit(f"    ld de,{row_stride}")
        compiler.emit("    add hl,de")
        compiler.emit("    pop de")
    compiler.emit(f"    djnz {row_loop}")


def _emit_flush(compiler) -> None:
    """Copy the classic graph buffer once after a complete drawing operation."""
    if compiler.target == "classic":
        compiler.emit("    bcall(_GrBufCpy)")


def _emit_text(compiler, node: ast.Call) -> None:
    keyword_args = {keyword.arg: keyword.value for keyword in node.keywords}
    if any(name not in ("color", "origin") for name in keyword_args) or len(keyword_args) != len(node.keywords):
        raise CompileError("text() accepts only the color and origin keywords")
    if len(node.args) not in (3, 4) or ("color" in keyword_args and len(node.args) == 4):
        raise CompileError('text() takes a string literal, x, y, and optional color')
    if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        raise CompileError("assembly graphics.text() requires a string literal")
    x0 = compiler.constant_integer(node.args[1])
    y0 = compiler.constant_integer(node.args[2])
    dynamic_position = x0 is None or y0 is None
    if dynamic_position and compiler.target != "ce":
        raise CompileError("runtime text coordinates currently require the CE target")
    if "color" in keyword_args:
        color = _color(compiler, keyword_args["color"], "text color", _default_color(compiler))
    elif len(node.args) == 4:
        color = _color(compiler, node.args[3], "text color", _default_color(compiler))
    else:
        color = _default_color(compiler)

    text = node.args[0].value
    if "\0" in text:
        raise CompileError("graphics.text() strings cannot contain NUL characters")
    origin = "top_left"
    if "origin" in keyword_args:
        origin_node = keyword_args["origin"]
        if not isinstance(origin_node, ast.Constant) or not isinstance(origin_node.value, str):
            raise CompileError('text() origin must be "top_left" or "center"')
        origin = origin_node.value.lower()
    if origin not in ("top_left", "center"):
        raise CompileError('text() origin must be "top_left" or "center"')
    if dynamic_position and origin != "top_left":
        raise CompileError('runtime text coordinates require origin="top_left"')

    if origin == "center" and compiler.target == "classic":
        screen_width, screen_height = 96, 64
        lines = text.split("\n")
        block_width = max((len(line) for line in lines), default=0) * 6
        block_height = max(1, len(lines)) * 8
        x0 += (screen_width - block_width) // 2
        y0 += (screen_height - block_height) // 2

    if compiler.target == "ce":
        try:
            encoded = text.encode("ascii") + b"\0"
        except UnicodeEncodeError as exc:
            raise CompileError("CE assembly graphics.text() supports ASCII strings only") from exc
        string_label = compiler.label("gfx_text")
        compiler.data_bytes(string_label, list(encoded))

        # CE OS font calls take 24-bit C ABI arguments on the stack:
        # (string pointer, pixel x, pixel y). Use the OS renderer instead of
        # writing each glyph directly into LCD VRAM.
        red = (color >> 11) & 0x1F
        green = (color >> 5) & 0x3F
        blue = color & 0x1F
        os_color = (blue << 11) | (green << 5) | red
        compiler.emit(f"    ld hl,{os_color}")
        compiler.emit("    push hl")
        compiler.emit("    call ti.os.SetDrawFGColor")
        compiler.emit("    pop hl")
        if origin == "center":
            # Ask the OS for the active font's real pixel metrics. The small
            # font can be proportional, so character-count estimates do not
            # reliably center text.
            compiler.emit("    call ti.os.FontGetHeight")
            compiler.emit("    ld de,240")
            compiler.emit("    ex de,hl")
            compiler.emit("    or a,a")
            compiler.emit("    sbc hl,de")
            compiler.emit("    srl h")
            compiler.emit("    rr l")
            if y0:
                compiler.emit(f"    ld de,{y0}")
                compiler.emit("    add hl,de")
            if y0 < 0:
                row_ok = compiler.label("gfx_text_row_ok")
                compiler.emit("    bit 7,h")
                compiler.emit(f"    jr z,{row_ok}")
                compiler.emit("    ld hl,0")
                compiler.emit(row_ok + ":")
            compiler.emit("    push hl")
            compiler.emit(f"    ld hl,{string_label}")
            compiler.emit("    push hl")
            compiler.emit("    call ti.os.FontGetWidth")
            # Preserve the returned width while removing its 24-bit argument.
            compiler.emit("    ex de,hl")
            compiler.emit("    ld hl,3")
            compiler.emit("    add hl,sp")
            compiler.emit("    ld sp,hl")
            # Restore the width from DE after cleaning the width-call argument.
            # Then compute (screen width - text width) / 2.
            compiler.emit("    ex de,hl")
            compiler.emit("    ld de,320")
            compiler.emit("    ex de,hl")
            compiler.emit("    or a,a")
            compiler.emit("    sbc hl,de")
            compiler.emit("    srl h")
            compiler.emit("    rr l")
            if x0:
                compiler.emit(f"    ld de,{x0}")
                compiler.emit("    add hl,de")
            if x0 < 0:
                col_ok = compiler.label("gfx_text_col_ok")
                compiler.emit("    bit 7,h")
                compiler.emit(f"    jr z,{col_ok}")
                compiler.emit("    ld hl,0")
                compiler.emit(col_ok + ":")
            compiler.emit("    push hl")
        else:
            # FontDrawText accepts pixel coordinates despite naming them
            # column and row.
            if y0 is None:
                compiler.expression(node.args[2])
            else:
                compiler.emit(f"    ld hl,{max(0, y0)}")
            compiler.emit("    push hl")
            if x0 is None:
                compiler.expression(node.args[1])
            else:
                compiler.emit(f"    ld hl,{max(0, x0)}")
            compiler.emit("    push hl")
        compiler.emit(f"    ld hl,{string_label}")
        compiler.emit("    push hl")
        compiler.emit("    call ti.os.FontDrawText")
        compiler.emit("    ld hl,9")
        compiler.emit("    add hl,sp")
        compiler.emit("    ld sp,hl")
        return

    if dynamic_position:
        raise CompileError("runtime text coordinates currently require the CE target")
    width, height = (96, 64) if compiler.target == "classic" else (320, 240)
    x, y = x0, y0
    for char in text:
        if char == "\n":
            x, y = x0, y + 8
            continue
        glyph = FONT_5X7.get(char.upper(), FONT_5X7["?"])
        for row, bits in enumerate(glyph):
            py = y + row
            if not 0 <= py < height:
                continue
            for col, bit in enumerate(bits):
                px = x + col
                if bit == "1" and 0 <= px < width:
                    _emit_pixel(compiler, px, py, color)
        x += 6
    _emit_flush(compiler)


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
    if compiler.target == "classic":
        # ILine draws an entire pixel-coordinate segment in ROM. Enable its
        # full-display bounds so x=95 and y=0 work like the rest of this API.
        compiler.emit("    res plotLoc,(iy+plotFlags)")
        compiler.emit("    set fullScrnDraw,(iy+apiFlg4)")
        compiler.emit(f"    ld bc,{x1 * 256 + 63 - y1}")
        compiler.emit(f"    ld de,{x2 * 256 + 63 - y2}")
        compiler.emit(f"    ld h,{color}")
        compiler.emit("    bcall(_ILine)")
        return
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
    if method not in ASSEMBLY_API:
        supported = ", ".join(f"graphics.{name}()" for name in sorted(ASSEMBLY_API))
        raise CompileError(f"standalone assembly graphics supports {supported}")

    if method == "sprite":
        _emit_sprite(compiler, node)
    elif method == "text":
        _emit_text(compiler, node)
    elif method in ("begin", "end") and not node.args and not node.keywords:
        if compiler.target == "ce":
            if method == "begin":
                compiler.emit("    call ti.RunIndicOff")
            if method == "end":
                compiler.emit("    call ti.DrawStatusBar")
                compiler.emit("    ei")
    elif method == "clear" and not node.args and not node.keywords:
        if compiler.target == "classic":
            compiler.emit("    bcall(_GrBufClr)")
            compiler.emit("    bcall(_GrBufCpy)")
        else:
            compiler.emit("    call ti.RunIndicOff")
            # Unlike the homescreen clear call, this clears all LCD VRAM,
            # including the status-bar area, and does not redraw the bar.
            compiler.emit("    call ti.boot.ClearVRAM")
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
    elif method == "delay" and len(node.args) == 1 and not node.keywords:
        cycles = literal_integer(node.args[0], "delay count", allow_unsigned=True)
        if not 1 <= cycles <= 65535:
            raise CompileError("delay() count must be from 1 to 65535")
        loop = compiler.label("gfx_delay")
        compiler.emit(f"    ld bc,{cycles}")
        compiler.emit(loop + ":")
        compiler.emit("    dec bc")
        compiler.emit("    ld a,b")
        compiler.emit("    or c")
        compiler.emit(f"    jr nz,{loop}")
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
        if compiler.target != "classic":
            _emit_flush(compiler)
    elif method == "rect":
        if node.keywords or len(node.args) not in (4, 5):
            raise CompileError("rect() takes x, y, width, height, and optional color")
        x, y, rect_width, rect_height = (literal_integer(arg, "rectangle values") for arg in node.args[:4])
        color = _color(compiler, node.args[4], "rectangle color", _default_color(compiler)) if len(node.args) == 5 else _default_color(compiler)
        screen_width, screen_height = (96, 64) if compiler.target == "classic" else (320, 240)
        if rect_width < 1 or rect_height < 1 or x + rect_width >= screen_width or y + rect_height >= screen_height:
            raise CompileError(f"rectangle must fit within the {screen_width}x{screen_height} screen")
        if compiler.target == "classic":
            upper_left = (y << 8) | x
            lower_right = ((y + rect_height) << 8) | (x + rect_width)
            compiler.emit("    res plotLoc,(iy+plotFlags)")
            compiler.emit(f"    ld hl,{upper_left}")
            compiler.emit(f"    ld de,{lower_right}")
            routine = "_EraseRectBorder" if color == 0 else "_DrawRectBorder"
            compiler.emit(f"    bcall({routine})")
        else:
            _emit_line(compiler, x, y, x + rect_width, y, color)
            _emit_line(compiler, x + rect_width, y, x + rect_width, y + rect_height, color)
            _emit_line(compiler, x + rect_width, y + rect_height, x, y + rect_height, color)
            _emit_line(compiler, x, y + rect_height, x, y, color)
        if compiler.target != "classic":
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
        if compiler.target != "classic":
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
        raise CompileError("graphics supports sprite(), text(), clear(), pixel(), line(), rect(), fill_rect(), triangle(), circle(), delay(), and wait_key()")
