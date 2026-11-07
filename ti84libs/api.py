"""The public ``ti84`` API: one table behind dispatch, errors, ``tipy-asm api``, and tests.

Adding a method means adding it here and implementing it in its library. A test
compiles and assembles every ``example`` on every target listed, and checks the
editor stubs in ``ti84/`` against this table, so the three cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

CE, CLASSIC = "ce", "classic"
BOTH = (CE, CLASSIC)


@dataclass(frozen=True)
class Method:
    signature: str
    doc: str
    example: str = ""            # statement using x, y, z (ints) and the library name
    targets: tuple[str, ...] = BOTH
    returns: bool = False
    note: str = ""               # shown when the method is unavailable on a target


def _m(signature: str, doc: str, example: str = "", targets: tuple[str, ...] = BOTH,
       returns: bool = False, note: str = "") -> Method:
    return Method(signature, doc, example, targets, returns, note)


_TEXT_NOTE = "the classic target draws text from literal coordinates; use graphics.text with constants"

API: dict[str, dict[str, Method]] = {
    "graphics": {
        "begin": _m("begin()", "Prepare the screen for drawing.", "graphics.begin()"),
        "end": _m("end()", "Restore the OS screen state.", "graphics.end()"),
        "clear": _m("clear()", "Clear the whole screen.", "graphics.clear()"),
        "fill_screen": _m("fill_screen(color=WHITE)", "Fill the whole screen with a color.",
                          "graphics.fill_screen(graphics.WHITE)"),
        "pixel": _m("pixel(x, y, color=BLACK)", "Set one pixel; off-screen runtime positions are clipped.",
                    "graphics.pixel(x, y, graphics.RED)"),
        "get_pixel": _m("get_pixel(x, y) -> int", "Read a pixel's RGB565 color.", "z = graphics.get_pixel(x, y)",
                        (CE,), True, "reading pixels needs the CE target"),
        "line": _m("line(x1, y1, x2, y2, color=BLACK)", "Draw a line.", "graphics.line(x, y, 5, 5, graphics.RED)"),
        "rect": _m("rect(x, y, width, height, color=BLACK)",
                   "Draw an outline covering x..x+width inclusive.", "graphics.rect(x, y, 5, 5, graphics.RED)"),
        "rectangle": _m("rectangle(x, y, width, height, color=BLACK)",
                        "Draw an outline exactly width by height pixels.", "graphics.rectangle(x, y, 5, 5, graphics.RED)"),
        "fill_rect": _m("fill_rect(x, y, width, height, color=BLACK)", "Draw a filled rectangle, clipped to the screen.",
                        "graphics.fill_rect(x, y, 5, 5, graphics.RED)"),
        "fill_rectangle": _m("fill_rectangle(x, y, width, height, color=BLACK)", "Same as fill_rect.",
                             "graphics.fill_rectangle(x, y, 5, 5, graphics.RED)"),
        "triangle": _m("triangle(x1, y1, x2, y2, x3, y3, color=BLACK)", "Draw a filled triangle.",
                       "graphics.triangle(x, y, 9, 0, 0, 9, graphics.RED)"),
        "circle": _m("circle(x, y, radius, color=BLACK)", "Draw a circle outline.", "graphics.circle(x, y, 5, graphics.RED)"),
        "fill_circle": _m("fill_circle(x, y, radius, color=BLACK)", "Draw a filled circle.",
                          "graphics.fill_circle(x, y, 5, graphics.RED)"),
        "horiz_line": _m("horiz_line(x, y, length, color=BLACK)", "Draw a fast horizontal line.",
                         "graphics.horiz_line(x, y, 5, graphics.RED)"),
        "vert_line": _m("vert_line(x, y, length, color=BLACK)", "Draw a fast vertical line.",
                        "graphics.vert_line(x, y, 5, graphics.RED)"),
        "text": _m("text(string, x, y, color=BLACK, *, origin='top_left')",
                   "Draw a literal string. Runtime coordinates need the CE target.", "graphics.text('HI', 1, 2)"),
        "text_int": _m("text_int(value, x, y, color=BLACK)", "Draw an integer, such as a score.",
                       "graphics.text_int(score, x, y)", (CE,), False, _TEXT_NOTE),
        "sprite": _m("sprite(pixels, x, y)", "Draw literal RGB565 rows; None is transparent.",
                     "graphics.sprite(((1, 2), (3, None)), x, y)"),
        "delay": _m("delay(count)", "Busy-wait for a count from 1 to 65535.", "graphics.delay(x)"),
        "wait_key": _m("wait_key()", "Wait for a key press.", "graphics.wait_key()"),
        "set_color": _m("set_color(color) -> int", "Set the Flash App's current color.", targets=(),
                        note="pass the color to each drawing call instead"),
        "save_cursor": _m("save_cursor(x, y)", "Save the 12 by 16 pixel screen area at x, y, so a cursor can be drawn over it.",
                          targets=(), note="redraw what a cursor covered yourself"),
        "restore_cursor": _m("restore_cursor()", "Put back the area saved by save_cursor().", targets=(),
                             note="redraw what a cursor covered yourself"),
    },
    "keyboard": {
        "read": _m("read() -> int", "Wait for a key press and return its code.", "z = keyboard.read()", returns=True),
        "get": _m("get() -> int", "Return the pressed key's code, or 0 at once if none. Use this in game loops.",
                  "z = keyboard.get()", returns=True),
        "is_down": _m("is_down(key) -> bool", "Whether a key is held now; several keys can be held together.",
                      "z = keyboard.is_down(keyboard.UP)", returns=True),
    },
    "math": {
        "abs": _m("abs(value) -> int", "Absolute value.", "z = math.abs(x)", returns=True),
        "min": _m("min(a, b) -> int", "Smaller value.", "z = math.min(x, y)", returns=True),
        "max": _m("max(a, b) -> int", "Larger value.", "z = math.max(x, y)", returns=True),
        "clamp": _m("clamp(value, low, high) -> int", "Limit a value to a range.", "z = math.clamp(x, 0, y)", returns=True),
        "sign": _m("sign(value) -> int", "-1, 0, or 1.", "z = math.sign(x)", returns=True),
        "sqrt": _m("sqrt(value) -> int", "Integer square root.", "z = math.sqrt(x)", returns=True),
        "pow": _m("pow(base, exponent) -> int", "Integer power; wraps at the target's integer width.",
                  "z = math.pow(x, 2)", returns=True),
        "sin": _m("sin(degrees) -> int", "Sine of an angle in degrees, scaled by 256.", "z = math.sin(x)", returns=True),
        "cos": _m("cos(degrees) -> int", "Cosine of an angle in degrees, scaled by 256.", "z = math.cos(x)", returns=True),
    },
    "random": {
        "seed": _m("seed(value)", "Seed the random number generator.", "random.seed(x)"),
        "randrange": _m("randrange(limit) -> int", "Random integer from 0 to limit - 1.", "z = random.randrange(x)", returns=True),
        "randint": _m("randint(low, high) -> int", "Random integer from low to high inclusive.",
                      "z = random.randint(x, y)", returns=True),
    },
    "storage": {
        "create": _m("create(name, size)", "Create a zero-filled AppVar unless it already exists.", "storage.create('SAVE', x)"),
        "exists": _m("exists(name) -> bool", "Whether an AppVar exists.", "z = storage.exists('SAVE')", returns=True),
        "size": _m("size(name) -> int", "An AppVar's size in bytes, or 0 if missing.", "z = storage.size('SAVE')", returns=True),
        "delete": _m("delete(name)", "Delete an AppVar if it exists.", "storage.delete('SAVE')"),
        "read_byte": _m("read_byte(name, offset) -> int", "Read a byte. A missing AppVar or bad offset ends the program.",
                        "z = storage.read_byte('SAVE', x)", returns=True),
        "write_byte": _m("write_byte(name, offset, value)",
                         "Write a byte. A missing or archived AppVar, or a bad offset, ends the program.",
                         "storage.write_byte('SAVE', x, y)"),
    },
    "file": {
        "exists": _m("exists(name) -> bool", "Whether an AppVar exists.", "z = file.exists('SAVE')", returns=True),
        "size": _m("size(name) -> int", "An AppVar's size in bytes, or 0 if missing.", "z = file.size('SAVE')", returns=True),
        "create": _m("create(name, size)", "Create a zero-filled AppVar unless it already exists.", "file.create('SAVE', x)"),
        "delete": _m("delete(name)", "Delete an AppVar if it exists.", "file.delete('SAVE')"),
        "clear": _m("clear(name)", "Zero every byte of an AppVar.", "file.clear('SAVE')"),
        "read_byte": _m("read_byte(name, offset) -> int", "Read a byte.", "z = file.read_byte('SAVE', x)", returns=True),
        "write_byte": _m("write_byte(name, offset, value)", "Write a byte.", "file.write_byte('SAVE', x, y)"),
        "read_u16": _m("read_u16(name, offset) -> int", "Read a little-endian 16-bit value.",
                       "z = file.read_u16('SAVE', x)", returns=True),
        "write_u16": _m("write_u16(name, offset, value)", "Write a little-endian 16-bit value.",
                        "file.write_u16('SAVE', x, y)"),
    },
    "sprite": {
        "load": _m("load(name) -> int", "Find a sprite AppVar built by [[tool.tipy.assets]]; 0 if missing.",
                   "hero = sprite.load('HERO')", (CE,), True, "AppVar sprites need the CE target; use graphics.sprite"),
        "draw": _m("draw(sprite, x, y)", "Draw a loaded sprite, clipped, with color 0 transparent.",
                   "sprite.draw(hero, x, y)", (CE,), note="AppVar sprites need the CE target; use graphics.sprite"),
        "width": _m("width(sprite) -> int", "A loaded sprite's width.", "z = sprite.width(hero)", (CE,), True,
                    "AppVar sprites need the CE target"),
        "height": _m("height(sprite) -> int", "A loaded sprite's height.", "z = sprite.height(hero)", (CE,), True,
                     "AppVar sprites need the CE target"),
    },
    "color": {
        "from_rgb": _m("from_rgb(r, g, b) -> int", "Make a screen color from 0-255 channels.",
                       "z = color.from_rgb(x, y, 0)", returns=True),
        "to_mono": _m("to_mono(color) -> int", "0 (white) for a bright color, 1 (black) for a dark one.",
                      "z = color.to_mono(x)", returns=True),
        "from_mono": _m("from_mono(mono) -> int", "Screen color for a mono value: 0 white, otherwise black.",
                        "z = color.from_mono(x)", returns=True),
        "is_valid": _m("is_valid(color) -> bool", "Whether a value is a valid color.", "z = color.is_valid(x)", returns=True),
        "invert": _m("invert(color) -> int", "Invert an RGB565 color.", "z = color.invert(x)", (CE,), True,
                     "the classic screen has no RGB colors"),
        "to_grayscale": _m("to_grayscale(color) -> int", "Convert an RGB565 color to gray.", "z = color.to_grayscale(x)",
                           (CE,), True, "the classic screen has no RGB colors"),
        "blend": _m("blend(color1, color2, factor=0.5) -> int", "Blend two constant colors at compile time.",
                    "z = color.blend(color.RED, color.BLUE)", (CE,), True,
                    "the classic screen has no RGB colors"),
    },
    "font": {},
    "graph": {
        "begin": _m("begin()", "Prepare the screen for drawing.", targets=(), note="use graphics.begin()"),
        "end": _m("end()", "Restore the OS screen state.", targets=(), note="use graphics.end()"),
    },
}

# Importable only for the Flash App backend.
FLASH_ONLY = ("graph",)
REPLACED = {"fileioc": "ti84.fileioc is not available; use ti84.storage or ti84.file for AppVars"}
NOT_IMPLEMENTED = {
    "sprite": "this sprite method is not implemented; available methods load and draw AppVar sprites",
    "font": "FontLibC fonts are not implemented, so ti84.font only provides color constants; use graphics.text()",
}


def flash_available(library: str, method: str) -> bool:
    """Whether the Flash App backend implements a method."""
    from ti84asm.cgen import KNOWN_MODULES
    from ti84asm.flash_ce import LIBRARY_C

    return library in KNOWN_MODULES and method in LIBRARY_C.get(f"ti84.{library}", {})


def format_api(library: str | None = None) -> str:
    """Render the API reference shown by ``tipy-asm api``."""
    if library is None:
        lines = ["Libraries (run 'tipy-asm api NAME' for details):"]
        for name, methods in API.items():
            lines.append(f"  {name:<10} {len(methods)} method(s)")
        lines.append("\nImport with: from ti84 import graphics, keyboard")
        return "\n".join(lines)
    if library not in API:
        raise KeyError(library)
    methods = API[library]
    lines = [f"ti84.{library}", ""]
    if library in NOT_IMPLEMENTED and not methods:
        lines.append(NOT_IMPLEMENTED[library])
    if library in FLASH_ONLY:
        lines.append("Flash App backend only; build with 'tipy-asm flash-app'.")
    for name, method in methods.items():
        where = [*method.targets]
        if flash_available(library, name):
            where.append("flash")
        lines.append(f"  {method.signature}")
        lines.append(f"      {method.doc}")
        lines.append(f"      targets: {', '.join(where) or 'none yet'}")
    return "\n".join(lines)
