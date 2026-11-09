"""CEdev's convfont in Python: FontLibC fonts from .fnt and text-format fonts.

This follows drdnar's convfont v1.2 (https://github.com/drdnar/convfont): the same
options, the same exit codes, and byte-for-byte the same output. It does not render
TTF or OTF files. Convert those to a .fnt or text-format font with a separate tool
first, then pass the result here with -f or -t.
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from .convbin import TYPE_APPVAR, ti_file
from .errors import CompileError

# Exit codes, as in convfont.h.
BAD_INFILE, BAD_OUTFILE, INVALID_FNT, BAD_OPTIONS, INTERNAL_ERROR, TEXT_PARSER_ERROR = 1, 2, 3, 4, 6, 7

MAX_APPVAR_SIZE = 0xFFE8
METADATA_STRUCT_SIZE = 21
MAX_FONTS = 64
HEADER_SIZE = 18

USAGE = "convfont -o <output format> -f <font FNT> [-metrics] [-f <font FNT 2> [-metrics]] <output file name>"
HELP = f"""Usage:
\t{USAGE}
\tSpecifying more than one input font is only valid for the font pack output format.

Output formats:
\t-o fontpack: A fontpack ready to be passed to convbin
\t-o carray: A C-style array
\t-o asmarray: An assembly-style array
\t-o binary: A straight binary blob
\t-Z: Use CR+LF newlines (default on Windows)
\t-z: Use LF newlines (default elsewhere)

Individual font properties:
\t-f: <file name> input Font
\t-t: <file name> input Text-format font
\t-a: <n> space Above
\t-b: <n> space Below
\t-i: <n> Italic space adjust
\t-w: <n> Weight
\t    The following strings may also be used:
\t        thin, extralight, light, semilight, normal, medium, semibold, bold, extrabold, black
\t-s: <n> Style
\t    The following strings may also be used:
\t        sans-serif, serif, upright, oblique, italic, monospaced, proportional
\t-c: <n> Cap height
\t-x: <n> x height
\t-l: <n> baseLine height
\tNumbers may be prefixed with 0x to specify hexadecimal instead of decimal.

Font pack properties:
\t-N: "<s>" font pack Name
\t-A: "<s>" Author
\t-C: "<s>" pseudoCopyright
\t-D: "<s>" Description
\t-V: "<s>" Version
\t-P: "<s>" code Page
"""

WEIGHTS = (("thin", 0x20), ("extra light", 0x30), ("extralight", 0x30), ("light", 0x40), ("semilight", 0x60),
           ("normal", 0x80), ("medium", 0x90), ("semibold", 0xA0), ("bold", 0xC0), ("extra bold", 0xE0),
           ("extrabold", 0xE0), ("black", 0xF0))
STYLES = (("sans-serif", 0), ("sansserif", 0), ("serif", 1), ("upright", 0), ("oblique", 2), ("italic", 4),
          ("monospaced", 8), ("fixed", 8), ("proportional", 0))
BOOLS = (("false", 0), ("f", 0), ("no", 0), ("n", 0), ("0", 0), ("nope", 0), ("nah", 0), ("nay", 0), ("true", 1),
         ("t", 1), ("yes", 1), ("y", 1), ("1", 1), ("yup", 1), ("yep", 1), ("yeah", 1), ("yea", 1), ("sure", 1))

_IGNORED, _EIGHT_BIT, _STYLE, _HEIGHT, _WEIGHT, _ITALIC, _CAP, _XHEIGHT, _BASELINE, _ABOVE, _BELOW, _DOUBLE_DEFAULT, \
    _WIDTH_DEFAULT, _FIXED, _INVERT_DEFAULT, _GLYPHS = range(16)
FONT_TAGS = tuple(
    (name, tag) for names, tag in (
        (("name", "description", "code page", "codepage", "copyright", "date"), _IGNORED),
        (("8bit", "8-bit", "8 bit", "force 8-bit", "force 8 bit", "eight-bit", "eight bit"), _EIGHT_BIT),
        (("height",), _HEIGHT), (("weight",), _WEIGHT), (("style",), _STYLE),
        (("italicadjust", "italicadjustment", "italic adjust", "italic adjustment", "italic_adjust",
          "italic_adjustment"), _ITALIC),
        (("cap", "capheight", "cap height", "cap_height"), _CAP),
        (("x", "xheight", "x height", "x-height", "x_height"), _XHEIGHT),
        (("baseline", "baselineheight", "baseline height", "baseline_height"), _BASELINE),
        (("above", "spaceabove", "space above", "space_above"), _ABOVE),
        (("below", "spacebelow", "space below", "space_below"), _BELOW),
        (("double", "doublewidth", "double width", "double_width"), _DOUBLE_DEFAULT),
        (("defaultwidth", "default width", "default_width", "width"), _WIDTH_DEFAULT),
        (("fixedwidth", "fixed width", "fixed_width"), _FIXED),
        (("invert", "inverted"), _INVERT_DEFAULT),
        (("glyphs", "characters", "bitmaps", "font data", "data", "[glyphs]", "[characters]", "[bitmaps]",
          "[font data]", "[data]"), _GLYPHS),
    ) for name in names)
_GLYPH_IGNORED, _CODEPOINT, _GLYPH_DOUBLE, _GLYPH_WIDTH, _GLYPH_INVERT, _GLYPH_DATA = range(6)
GLYPH_TAGS = tuple(
    (name, tag) for names, tag in (
        (("name", "unicode", "[character]", "[char]", "[glyph]", "[next]"), _GLYPH_IGNORED),
        (("double", "doublewidth", "double width", "double_width"), _GLYPH_DOUBLE),
        (("codepoint", "code point", "index", "code"), _CODEPOINT),
        (("width",), _GLYPH_WIDTH), (("invert", "inverted"), _GLYPH_INVERT),
        (("data", "image", "bitmap", "[data]", "[image]", "[bitmap]"), _GLYPH_DATA),
    ) for name in names)

_SPACES = {0xA0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x202F, 0x205F,
           0x2012, 0x2013, 0x2014, 0x2212, 0x3000}
_SKIPPED = {0xAD, 0x2009, 0x200A, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}
_SINGLE_QUOTES = {0x2018, 0x2019, 0x201A, 0x201B, 0x2039, 0x203A, 0x231C, 0x231D, 0x300C, 0x300D, 0xFE41, 0xFE42,
                  0xFF07, 0xFF62, 0xFF63}
_DOUBLE_QUOTES = {0xAB, 0xBB, 0x201C, 0x201D, 0x201E, 0x201F, 0x2E42, 0x300E, 0x300F, 0x301D, 0x301E, 0x301F,
                  0xFE43, 0xFE44, 0xFF02}
_ESCAPES = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11}
_UNKNOWN, _ASCII, _UTF8, _UTF16BE, _UTF16LE = range(5)
_START, _NEXT = range(2)
_MAX_LINE = 256
_EOF, _LINE_TOO_LONG = -1, -11007


class FontError(CompileError):
    """A conversion failure, carrying the exit code convfont uses for it."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Font:
    height: int
    first_glyph: int
    widths: list[int]
    bitmaps: list[bytes]        # row-major, with each row's bytes left to right
    italic_space_adjust: int = 0
    space_above: int = 0
    space_below: int = 0
    weight: int = 0
    style: int = 0
    cap_height: int = 0
    x_height: int = 0
    baseline_height: int = 0

    @property
    def total_glyphs(self) -> int:
        return len(self.widths)


def byte_columns(width: int) -> int:
    return ((width - 1) >> 3) + 1


def _lookup(text: str, table: tuple) -> int:
    """convfont's string match: comparing stops at the end of the shorter string."""
    for name, value in table:
        if all(a.lower() == b for a, b in zip(text, name)):
            return value
    return -1


def _strtol(text: str) -> int:
    """C's strtol(text, NULL, 0): 0x is hex, a leading 0 is octal, and junk reads as 0."""
    text = text.lstrip(" \t\n\r\f\v")
    sign = 1
    if text[:1] in ("+", "-"):
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    if text[:2].lower() == "0x" and text[2:3] and text[2] in "0123456789abcdefABCDEF":
        base, text = 16, text[2:]
    elif text[:1] == "0":
        base = 8
    else:
        base = 10
    value = 0
    for char in text:
        digit = "0123456789abcdef".find(char.lower())
        if digit < 0 or digit >= base:
            break
        value = value * base + digit
    return sign * value


# ------------------------------------------------------------------ FNT files
def _word(data: bytes, at: int) -> int:
    if at + 2 > len(data):
        raise FontError(INVALID_FNT, "Out of WORDs in input.")
    return struct.unpack_from("<h", data, at)[0]


def _dword(data: bytes, at: int) -> int:
    if at + 4 > len(data):
        raise FontError(INVALID_FNT, "Out of DWORDs in input.")
    return struct.unpack_from("<i", data, at)[0]


def _byte(data: bytes, at: int) -> int:
    if at >= len(data):
        raise FontError(INVALID_FNT, "Out of BYTEs in input.")
    return data[at]


def parse_fnt(data: bytes) -> Font:
    """Read a raster Windows FNT, version 2 or 3."""
    version = _word(data, 0)
    if version not in (0x200, 0x300):
        raise FontError(BAD_INFILE, "-f: Input file does not appear to be an FNT at all.")
    size = _dword(data, 2)
    if size > len(data):
        raise FontError(INVALID_FNT, "dfSize extends past end of file.")
    if _word(data, 66) & 1:
        raise FontError(INVALID_FNT, "Not a raster font.")
    ascent = _word(data, 74)
    height = _word(data, 88) & 0xFF
    first, last = _byte(data, 95), _byte(data, 96)
    at = 118
    if version == 0x300:
        flags = _dword(data, at)
        if flags & 0x0C:
            raise FontError(INVALID_FNT, "DEF_ABC* is not supported.")
        if flags & 0xF0 != 0x10:
            raise FontError(INVALID_FNT, "DFF_1COLOR is required.")
        at += 24 + 6        # the rest of the header, then a dummy table entry
    entries = []
    for _ in range(last - first + 1):
        width = _word(data, at)
        offset = (data[at + 2] | data[at + 3] << 8) if version == 0x200 and at + 4 <= len(data) else None
        if version == 0x200:
            if offset is None:
                raise FontError(INVALID_FNT, "Out of WORDs in input.")
            at += 4
        else:
            offset = _dword(data, at + 2)
            at += 6
        if offset > size:
            raise FontError(INVALID_FNT, "Glyph bitmap location offset is past declared end of FNT struct.")
        entries.append((width, offset))
    if last < first:
        raise FontError(INVALID_FNT, "Negative bitmaps present! (dfFirstChar > dfLastChar)")
    widths, bitmaps = [], []
    for width, offset in entries:
        if width > 24 or width < 0:
            raise FontError(INVALID_FNT, "Glyph widths greater than 24 are not supported.")
        if width == 0:
            raise FontError(INVALID_FNT, "Zero-width glyph is a bad idea.")
        columns = byte_columns(width)
        if offset + columns * height > len(data):
            raise FontError(INVALID_FNT, "Out of BYTEs in input.")
        # FNT stores glyphs column by column; FontLibC wants rows.
        bitmap = bytearray(columns * height)
        for column in range(columns):
            for row in range(height):
                bitmap[row * columns + column] = data[offset + column * height + row]
        widths.append(width)
        bitmaps.append(bytes(bitmap))
    return Font(height, first, widths, bitmaps, baseline_height=ascent & 0xFF)


# ----------------------------------------------------------- text-format fonts
class _TextParser:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.encoding = _UNKNOWN
        self.bom_found = False
        self.expecting = _START
        self.line_number = 1
        self.line = ""
        self.pending: int | None = None

    def fail(self, message: str) -> None:
        raise FontError(TEXT_PARSER_ERROR, f"Line {self.line_number}: {message}")

    def raw(self) -> int:
        if self.pos >= len(self.data):
            self.pos += 1
            return _EOF
        self.pos += 1
        return self.data[self.pos - 1]

    def raw_or_fail(self, message: str) -> int:
        value = self.raw()
        if value < 0:
            self.fail(message)
        return value

    def next_char(self) -> int:
        if self.pending is not None:
            value, self.pending = self.pending, None
            return value
        c = self.raw()
        if c < 0:
            return c
        if self.encoding in (_UTF16BE, _UTF16LE):
            c2 = self.raw_or_fail("UTF-16 decoder: Failed to get second byte of UTF-16 pair.")
            c = (c << 8) | c2 if self.encoding == _UTF16BE else (c2 << 8) | c
            if 0xD800 <= c < 0xDC00:
                if self.expecting == _NEXT:
                    self.fail("UTF-16 decoder: Two first halves of surrogate pair.")
                self.expecting = _NEXT
                c2 = self.next_char()
                self.expecting = _START
                if c2 < 0:
                    self.fail("UTF-16 decoder: Failed to get second half of surrogate pair.")
                c = 0x10000 + ((c2 & 0x3FF) | ((c & 0x3FF) << 10))
            elif 0xDC00 <= c < 0xE000:
                if self.expecting == _START:
                    self.fail("UTF-16 decoder: Unexpected second half of surrogate pair.")
            elif self.expecting == _NEXT:
                self.fail("UTF-16 decoder: Expected second half of surrogate pair.")
        elif self.encoding == _UTF8:
            if c >= 0xF5:
                self.fail("UTF-8 decoder: Invalid byte >= 0xF5.")
            if c >= 0xC2:
                if c >= 0xF0:
                    c, required = c & 7, 3
                elif c >= 0xE0:
                    c, required = c & 0xF, 2
                else:
                    c, required = c & 0x1F, 1
                for _ in range(required):
                    c2 = self.raw_or_fail("UTF-8 decoder: Failed to get subsequent byte(s) of multibyte sequence.")
                    if not 0x80 <= c2 < 0xC0:
                        self.fail("UTF-8 decoder: Expected subsequent byte.")
                    c = (c << 6) | (c2 & 0x3F)
                if 0xD800 <= c < 0xE000:
                    self.fail("UTF-8 decoder: Surrogate pair encoded.")
            elif c >= 0x80:
                self.fail("UTF-8 decoder: Continuation byte(s) without leading byte.")
        if c == 0:
            self.fail("Null in input text.")
        return c

    def next(self) -> int:
        """Read a character, folding newlines and Unicode punctuation as convfont does."""
        while True:
            c = self.next_char()
            if c < 0:
                return c
            if self.encoding > _ASCII:
                if c in _SPACES:
                    c = ord(" ")
                elif c in _SKIPPED or 0x300 <= c < 0x370:
                    continue
                elif c in _SINGLE_QUOTES:
                    c = ord("'")
                elif c in _DOUBLE_QUOTES:
                    c = ord('"')
            if c != ord("\r"):
                return c
            c = self.next_char()
            if c < 0:
                return c
            if c != ord("\n"):
                self.pending = c
            return ord("\n")

    def read_header(self) -> None:
        c = self.raw_or_fail("Out of bytes in header.")
        c2 = self.raw_or_fail("Out of bytes in header.")
        ini = False
        wrong = 'File does not start with "convfont".'

        def is_c(value: int) -> bool:
            return value in (ord("c"), ord("C"))

        if c >= 0xFE:
            if (c, c2) == (0xFE, 0xFF):
                self.encoding = _UTF16BE
            elif (c, c2) == (0xFF, 0xFE):
                self.encoding = _UTF16LE
            else:
                self.fail("BOM-like bytes not valid.")
            c2 = self._header_char()
            ini = c2 == ord("[")
            if ini:
                c2 = self._header_char()
            if not is_c(c2):
                self.fail(wrong)
        elif c == 0xEF:
            if c2 != 0xBB or self.raw_or_fail("Out of bytes in header.") != 0xBF:
                self.fail(wrong)
            self.encoding = _UTF8
            c2 = self._header_char()
            ini = c2 == ord("[")
            if ini:
                c2 = self._header_char()
            if not is_c(c2):
                self.fail(wrong)
            self.bom_found = True
        elif c2 == 0 and (is_c(c) or c == ord("[")):
            ini = c == ord("[")
            if ini:
                c = self.raw_or_fail("Out of bytes in header.")
                c2 = self.raw_or_fail("Out of bytes in header.")
                if not is_c(c):
                    self.fail(wrong)
                if c2 != 0:
                    self.fail("Corrupted encoding.")
            self.encoding = _UTF16LE
        elif c == 0 and (is_c(c2) or c2 == ord("[")):
            ini = c2 == ord("[")
            if ini:
                c = self.raw_or_fail("Out of bytes in header.")
                c2 = self.raw_or_fail("Out of bytes in header.")
                if c != 0:
                    self.fail("Corrupted encoding.")
                if not is_c(c2):
                    self.fail(wrong)
            self.encoding = _UTF16BE
        elif is_c(c) or c == ord("["):
            ini = c == ord("[")
            if ini:
                c = self.raw_or_fail("Out of bytes in header.")
                if not is_c(c):
                    self.fail(wrong)
            self.pos -= 1       # give back c2
        else:
            self.fail(wrong)
        for expected in "onvfont":
            value = self._header_char()
            if chr(value).lower() != expected:
                self.fail(wrong)
        c = self.next()
        if ini and c == ord("]"):
            c = self.next()
        if c != ord("\n"):
            self.fail('File does not start with "convfont" and newline.')
        if self.encoding == _UNKNOWN:
            self.encoding = _UTF8

    def _header_char(self) -> int:
        value = self.next_char()
        if value < 0:
            self.fail("Out of bytes in header.")
        return value

    def next_line(self) -> int:
        """Buffer a line; return 0, _EOF, or _LINE_TOO_LONG."""
        c = _EOF
        remaining = _MAX_LINE
        self.line_number += 1
        chars: list[str] = []
        while True:
            remaining -= 1
            if remaining <= 0:
                self.line = "".join(chars)
                while c != ord("\n") and c > 0:
                    c = self.next()
                return _LINE_TOO_LONG
            c = self.next()
            if c < 0:
                self.line = "".join(chars)
                return c if not chars else 0
            if c == ord("\n"):
                self.line = "".join(chars)
                return 0
            chars.append(chr(min(c, 0xFF)))

    def check(self, value: int) -> None:
        if value == _LINE_TOO_LONG:
            self.fail("Line too long.")
        if value == _EOF:
            self.fail("Unexpected end of data.")

    def fields(self) -> tuple[str, str]:
        """Split the current line into its tag and value."""
        tag: list[str] = []
        text = self.line.lstrip(" \t")
        index = 0
        while True:
            if index >= len(text):
                self.fail("Tag expected.")
            char = text[index]
            index += 1
            if char in ":=]":
                if char == "]":
                    tag.append("]")
                break
            if char in " \t":
                tag.append(" ")
                while index < len(text) and text[index] in " \t":
                    index += 1
                continue
            tag.append(char)
        value: list[str] = []
        rest = text[index:].lstrip(" \t")
        index = 0
        while index < len(rest):
            char = rest[index]
            index += 1
            if char in " \t":
                value.append(" ")
                while index < len(rest) and rest[index] in " \t":
                    index += 1
                continue
            value.append(char)
        return _strip_one_space("".join(tag)), _strip_one_space("".join(value))

    def number(self, text: str) -> int:
        """Read a number: decimal, 0x, $, U+, or a character literal."""
        text = text.lstrip(" \t")
        c = text[:1]
        if c in ("'", '"') and c:
            return self._char_literal(text)
        if c in ("U", "u"):
            if text[1:2] != "+":
                self.fail("Invalid Unicode identifier.")
            return self._limit(_leading_hex(text[2:]))
        if c == "$":
            return self._limit(_leading_hex(text[1:]))
        if c == "0":
            following = text[1:2].lower()
            if following == "x":
                if not text[2:3] or text[2] not in "0123456789abcdefABCDEF":
                    self.fail("Invalid hexadecimal number.")
                return self._limit(_leading_hex(text[2:]))
            if not following.isdigit():
                return 0
        if c and c in "0123456789":
            digits = ""
            for char in text:
                if char not in "0123456789":
                    break
                digits += char
            return self._limit(int(digits))
        self.fail("Invalid number.")

    def _limit(self, value: int) -> int:
        if value > 0x7FFFFFFF:
            self.fail("Overflow parsing number.")
        return value

    def _char_literal(self, text: str) -> int:
        quote = text[0]
        invalid = "Invalid char literal."
        if len(text) < 2 or text[1] in ("\n", "'" if quote == "'" else '"'):
            self.fail(invalid)
        index = 2
        char = text[1]
        if char != "\\":
            value = ord(char)
        else:
            if index >= len(text):
                self.fail(invalid)
            char = text[index]
            index += 1
            if char in _ESCAPES:
                value = _ESCAPES[char]
            elif char == "x":
                digits = _hex_prefix(text[index:])
                if not digits:
                    self.fail("Invalid hexadecimal escape sequence in char literal.")
                value = int(digits, 16)
                index += len(digits)
            elif char in "01234567":
                digits = char
                while len(digits) < 3 and text[index:index + 1] in tuple("01234567"):
                    digits += text[index]
                    index += 1
                value = int(digits, 8)
            elif char in "Uu":
                count = 8 if char == "U" else 4
                digits = _hex_prefix(text[index:index + count])
                if len(digits) != count:
                    self.fail("Invalid Unicode escape sequence in char literal.")
                value = int(digits, 16)
                index += count
            else:
                value = ord(char)
        if text[index:index + 1] != quote:
            self.fail(invalid)
        return value

    def boolean(self, text: str) -> int:
        value = _lookup(text, BOOLS)
        if value < 0:
            self.fail("Invalid boolean.")
        return value


def _strip_one_space(text: str) -> str:
    return text[:-1] if text.endswith(" ") else text


def _hex_prefix(text: str) -> str:
    digits = ""
    for char in text:
        if char not in "0123456789abcdefABCDEF":
            break
        digits += char
    return digits


def _leading_hex(text: str) -> int:
    digits = _hex_prefix(text)
    return int(digits, 16) if digits else 0


def _parse_bitmap(text: str, double_width: bool) -> tuple[int, int]:
    """Return (pixels, width), with the first pixel in the top bit of 32."""
    pixels, width, bit, index = 0, 0, 0x80000000, 0
    while index < len(text):
        if text[index] not in "0 ":
            pixels |= bit
        index += 1
        bit >>= 1
        width += 1
        if double_width:
            if index >= len(text):
                break
            index += 1
    return pixels, width


def parse_text(data: bytes) -> Font:
    """Read a text-format font, as with convfont -t."""
    state = _TextParser(data)
    state.read_header()
    metrics = {key: -1 for key in ("italic", "cap", "x", "baseline", "above", "below", "style", "weight")}
    forced_8_bit = default_double = fixed_width = False
    default_inverted = 0
    default_width = height = -1
    single = {_ITALIC: ("italic", "Italic adjust"), _CAP: ("cap", "Capital height"), _XHEIGHT: ("x", "X height"),
              _BASELINE: ("baseline", "Baseline height"), _ABOVE: ("above", "Space above"),
              _BELOW: ("below", "Space below")}
    while True:
        result = state.next_line()
        stripped = state.line.lstrip(" \t")
        state.check(result)
        if not stripped or stripped[0] in ":#":
            continue
        tag, value = state.fields()
        kind = _lookup(tag, FONT_TAGS)
        if kind < 0:
            state.fail("Unrecognized tag.")
        if kind == _GLYPHS:
            break
        if kind == _EIGHT_BIT:
            if forced_8_bit:
                state.fail("Duplicate specifier of 8-bit encoding mode.")
            forced_8_bit = True
            if state.boolean(value):
                if state.encoding in (_UTF16BE, _UTF16LE):
                    state.fail("Detected UTF-16 encoding, but 8-bit encoding requested.")
                if state.encoding == _UTF8 and state.bom_found:
                    state.fail("Detected UTF-8 encoding, but 8-bit encoding requested.")
                state.encoding = _ASCII
        elif kind == _HEIGHT:
            if height != -1:
                state.fail("Duplicate height tag.")
            height = state.number(value)
            if not 1 <= height <= 255:
                state.fail("Invalid height.")
        elif kind == _WIDTH_DEFAULT:
            if fixed_width:
                state.fail("Fixed-width and default width tags are mutually exclusive.")
            if default_width != -1:
                state.fail("Duplicate width tag.")
            default_width = state.number(value)
            if default_width < 1:
                state.fail("Invalid default width.")
        elif kind in single:
            key, label = single[kind]
            if metrics[key] != -1:
                state.fail(f"{label} already set.")
            metrics[key] = state.number(value)
        elif kind == _STYLE:
            found = _lookup(value, STYLES)
            metrics["style"] = max(metrics["style"], 0) | (found if found >= 0 else state.number(value))
        elif kind == _WEIGHT:
            if metrics["weight"] != -1:
                state.fail("Duplicate weight tag.")
            found = _lookup(value, WEIGHTS)
            metrics["weight"] = found if found >= 0 else state.number(value)
        elif kind == _DOUBLE_DEFAULT:
            default_double = bool(state.boolean(value))
        elif kind == _FIXED:
            if fixed_width:
                state.fail("Duplicate fixed-width tag.")
            if default_width != -1:
                state.fail("Fixed-width and default width tags are mutually exclusive.")
            fixed_width = True
            default_width = state.number(value)
            if default_width < 1:
                state.fail("Invalid fixed width.")
        elif kind == _INVERT_DEFAULT:
            default_inverted = 255 if state.boolean(value) else 0
    if height == -1:
        state.fail("Need to set font's height.")

    widths: dict[int, int] = {}
    bitmaps: dict[int, bytes] = {}
    codepoint, first_glyph = 0, 256
    done = False
    while not done:
        double_width, inverted = default_double, default_inverted
        width = -1
        got_tags = False
        while True:
            result = state.next_line()
            stripped = state.line.lstrip(" \t")
            if result == _EOF and not stripped:
                if got_tags:
                    state.fail("Unexpected end of file.")
                done = True
                break
            if not stripped or stripped[0] in ":#":
                continue
            state.check(result)
            tag, value = state.fields()
            kind = _lookup(tag, GLYPH_TAGS)
            if kind < 0:
                state.fail("Unrecognized tag.")
            if kind == _GLYPH_DATA:
                break
            got_tags = True
            if kind == _CODEPOINT:
                codepoint = state.number(value)
                if codepoint > 255:
                    state.fail("Cannot have code point greater than 255.")
            elif kind == _GLYPH_DOUBLE:
                double_width = bool(state.boolean(value))
            elif kind == _GLYPH_WIDTH:
                if width != -1:
                    state.fail("Duplicate width tag.")
                width = state.number(value)
                if fixed_width and width != default_width:
                    state.fail("Fixed-width is active; cannot override width.")
                if not 1 <= width <= 24:
                    state.fail("Invalid width.")
            elif kind == _GLYPH_INVERT:
                inverted = 255 if state.boolean(value) else 0
        if done:
            break
        if codepoint > 255:
            state.fail("Too many code points.")
        near = f"Near line {state.line_number} processing code point {codepoint} (0x02X): "
        if codepoint in bitmaps:
            raise FontError(TEXT_PARSER_ERROR, near + "Duplicate code point definition.")
        rows = []
        glyph_width = 0
        for _ in range(height):
            state.check(state.next_line())
            pixels, row_width = _parse_bitmap(state.line, double_width)
            rows.append(pixels)
            glyph_width = max(glyph_width, row_width)
        if fixed_width:
            if glyph_width > default_width:
                raise FontError(TEXT_PARSER_ERROR, near + "Bitmap is wider than specified fixed width.")
            width = default_width
        elif width == -1:
            width = max(glyph_width, default_width)
        elif glyph_width > width:
            raise FontError(TEXT_PARSER_ERROR, near + "Bitmap wider than manually set width.")
        if width < 1:
            raise FontError(TEXT_PARSER_ERROR, near + "Invalid width.  Try setting a width manually.")
        if width > 24:
            raise FontError(TEXT_PARSER_ERROR, near + "Invalid width.")
        columns = byte_columns(width)
        bitmap = bytearray()
        for pixels in rows:
            for column in range(columns):
                bitmap.append(((pixels >> (24 - 8 * column)) & 0xFF) ^ inverted)
        widths[codepoint] = width
        bitmaps[codepoint] = bytes(bitmap)
        first_glyph = min(first_glyph, codepoint)
        codepoint += 1
    if not bitmaps:
        raise FontError(TEXT_PARSER_ERROR, "Reached end of file without reading any glyphs.")
    count = len(bitmaps)
    for point in range(first_glyph, first_glyph + count):
        if point not in bitmaps:
            raise FontError(TEXT_PARSER_ERROR, f"Need definition for code point {point} (0x{point:02X}).")
    order = range(first_glyph, first_glyph + count)

    def metric(key: str) -> int:
        return metrics[key] & 0xFF if metrics[key] >= 0 else 0

    return Font(height, first_glyph, [widths[point] for point in order], [bitmaps[point] for point in order],
                metric("italic"), metric("above"), metric("below"), metric("weight"), metric("style"),
                metric("cap"), metric("x"), metric("baseline"))


# --------------------------------------------------------------------- output
def _ezword(value: int) -> bytes:
    return bytes((value & 255, (value >> 8) & 255, (value >> 16) & 255))


def serialize_font(font: Font) -> bytes:
    """Write the FontLibC binary format."""
    total = font.total_glyphs
    out = bytearray((0, font.height, total & 0xFF, font.first_glyph))
    out += _ezword(HEADER_SIZE) + _ezword(HEADER_SIZE + total)
    out += bytes((font.italic_space_adjust, font.space_above, font.space_below, font.weight, font.style,
                  font.cap_height, font.x_height, font.baseline_height))
    out += bytes(font.widths)
    next_bitmap = HEADER_SIZE + total * 3
    for width, bitmap in zip(font.widths, font.bitmaps):
        out += struct.pack("<H", (next_bitmap - 2 + byte_columns(width) - 1) & 0xFFFF)
        next_bitmap += len(bitmap)
        if next_bitmap >= MAX_APPVAR_SIZE:
            raise FontError(INVALID_FNT, "Output font too big to fit!")
    for width, bitmap in zip(font.widths, font.bitmaps):
        columns = byte_columns(width)
        for row in range(font.height):
            out += bitmap[row * columns:(row + 1) * columns][::-1]
    return bytes(out)


def compute_font_size(font: Font) -> int:
    return HEADER_SIZE + 3 * font.total_glyphs + sum(len(bitmap) for bitmap in font.bitmaps)


def serialize_fontpack(fonts: list[Font], metadata: dict[str, bytes] | None = None) -> bytes:
    """Write a FONTPACK. ``metadata`` keys are the -N, -A, -C, -D, -V, and -P options."""
    strings = [(metadata or {}).get(key) for key in "NACDVP"]
    out = bytearray(b"FONTPACK")
    location = 12 + len(fonts) * 3
    has_metadata = any(text is not None for text in strings)
    if has_metadata:
        out += _ezword(location)
        location += METADATA_STRUCT_SIZE
    else:
        out += _ezword(0)
    string_location = location
    location += sum(len(text) + 1 for text in strings if text is not None)
    out.append(len(fonts))
    for font in fonts:
        out += _ezword(location)
        location += compute_font_size(font)
    if location >= MAX_APPVAR_SIZE:
        raise FontError(BAD_OPTIONS, "Cannot form appvar; output appvar size would exceed 64 K appvar size limit.")
    if has_metadata:
        out += _ezword(METADATA_STRUCT_SIZE)
        for text in strings:
            if text is None:
                out += _ezword(0)
            else:
                out += _ezword(string_location)
                string_location += len(text) + 1
        for text in strings:
            if text is not None:
                out += text + b"\0"
    for font in fonts:
        out += serialize_font(font)
    return bytes(out)


def to_c_array(data: bytes, newline: bytes) -> bytes:
    rows = [b", ".join(b"0x%02X" % value for value in data[start:start + 16]) for start in range(0, len(data), 16)]
    return (b"," + newline).join(rows) + newline


def to_asm_array(font: Font, newline: bytes) -> bytes:
    lines = [
        b".header:",
        b"\tdb\t0 ; font format version",
        b"\tdb\t%d ; height" % font.height,
        b"\tdb\t%d ; glyph count" % (font.total_glyphs & 0xFF),
        b"\tdb\t%d ; first glyph" % font.first_glyph,
        b"\tdl\t.widthsTable - .header ; offset to widths table",
        b"\tdl\t.bitmapsTable - .header ; offset to bitmaps offsets table",
        b"\tdb\t%d ; italics space adjust" % font.italic_space_adjust,
        b"\tdb\t%d ; suggested blank space above" % font.space_above,
        b"\tdb\t%d ; suggested blank space below" % font.space_below,
        b"\tdb\t%d ; weight (boldness/thinness)" % font.weight,
        b"\tdb\t%d ; style field" % font.style,
        b"\tdb\t%d ; capital height" % font.cap_height,
        b"\tdb\t%d ; lowercase x height" % font.x_height,
        b"\tdb\t%d ; baseline height" % font.baseline_height,
        b".widthsTable: ; start of widths table",
    ]
    points = [font.first_glyph + index for index in range(font.total_glyphs)]
    for width, point in zip(font.widths, points):
        lines.append(b"\tdb\t%d ; Code point $%02X %c" % (width, point, point & 0xFF))
    lines.append(b".bitmapsTable: ; start of table of offsets to bitmaps")
    for width, point in zip(font.widths, points):
        adjust = b" - %d" % (3 - byte_columns(width)) if width <= 16 else b""
        lines.append(b"\tdw\t.glyph_%02X - .header%s; %c" % (point, adjust, point & 0xFF))
    for width, point, bitmap in zip(font.widths, points, font.bitmaps):
        columns = byte_columns(width)
        lines.append(b".glyph_%02X: ; %c" % (point, point & 0xFF))
        directive = {1: b"db", 2: b"dw", 3: b"dl"}[columns]
        for row in range(font.height):
            pixels = bitmap[row * columns:(row + 1) * columns]
            lines.append(b"\t%s\t%sb" % (directive, b"".join(format(value, "08b").encode() for value in pixels)))
    return newline.join(lines) + newline


def load_font(path: Path) -> Font:
    """Read a font file for a project asset, choosing the parser by its suffix."""
    suffix = path.suffix.lower()
    if suffix in (".ttf", ".otf"):
        raise CompileError(f"{path}: convfont does not read {suffix} files; convert it to a .fnt or "
                           "text-format font with a separate tool first")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CompileError(f"cannot read {path}: {exc.strerror or exc}") from exc
    return parse_fnt(data) if suffix == ".fnt" else parse_text(data)


def font_appvar(sources, output: Path, name: str, metadata: dict[str, str] | None = None) -> Path:
    """Write a project font asset: an archived AppVar holding a FONTPACK of one font or several.

    ``metadata`` maps convfont's metadata letters (N family, A author, C copyright,
    D description, V version) to their text.
    """
    if isinstance(sources, Path):
        sources = [sources]
    encoded = {}
    for letter, text in (metadata or {}).items():
        try:
            encoded[letter] = text.encode("ascii")
        except UnicodeEncodeError as exc:
            raise FontError(BAD_OPTIONS, f"font {letter} metadata must be ASCII: {text!r}") from exc
    pack = serialize_fontpack([load_font(source) for source in sources], encoded or None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(ti_file(TYPE_APPVAR, name, pack, archived=True))
    return output


# --------------------------------------------------------------- command line
_FLAGS = set("hvZz")
_WITH_VALUE = set("ofabiwscxlNACDVPt")
_METADATA_LIMITS = {"N": 4096, "A": 4096, "D": 4096, "V": 4096}


def _options(argv: list[str]):
    """Walk arguments like GNU getopt: options may follow the output file name."""
    positional: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        index += 1
        if argument == "--":
            positional.extend(argv[index:])
            break
        if not argument.startswith("-") or argument == "-":
            positional.append(argument)
            continue
        position = 1
        while position < len(argument):
            letter = argument[position]
            position += 1
            if letter in _FLAGS:
                yield letter, ""
            elif letter in _WITH_VALUE:
                if position < len(argument):
                    yield letter, argument[position:]
                elif index < len(argv):
                    yield letter, argv[index]
                    index += 1
                else:
                    raise FontError(BAD_OPTIONS, "Unknown option; check syntax.")
                break
            else:
                raise FontError(BAD_OPTIONS, "Unknown option; check syntax.")
    yield None, positional


def _read_input(letter: str, name: str) -> Font:
    try:
        data = Path(name).read_bytes()
    except OSError as exc:
        raise FontError(BAD_INFILE, "-f: Cannot open input file.") from exc
    return parse_fnt(data) if letter == "f" else parse_text(data)


def _set_metric(font: Font | None, letter: str, value: str) -> None:
    if font is None:
        raise FontError(BAD_OPTIONS, f"-{letter}: Must specify a font before specifying metrics.")
    too_far = FontError(BAD_OPTIONS, f"-{letter}: Number too large or small.")
    if letter in "ws":
        number = _lookup(value, WEIGHTS if letter == "w" else STYLES)
        if number == -1:
            number = _strtol(value)
            if not 0 <= number <= 255:
                raise too_far
        if letter == "w":
            font.weight = number
        else:
            font.style |= number
        return
    number = _strtol(value)
    limit = {"a": 64, "b": 64, "i": 24}.get(letter, font.height)
    if not 0 <= number <= limit:
        raise too_far
    field = {"a": "space_above", "b": "space_below", "i": "italic_space_adjust", "c": "cap_height",
             "x": "x_height", "l": "baseline_height"}[letter]
    setattr(font, field, number)


def convert(argv: list[str]) -> int:
    """Run a convfont command line, raising FontError on failure."""
    fonts: list[Font] = []
    current: Font | None = None
    output_format = ""
    metadata: dict[str, bytes] = {}
    newline = b"\r\n" if sys.platform == "win32" else b"\n"
    positional: list[str] = []
    for letter, value in _options(argv):
        if letter is None:
            positional = value
        elif letter == "h":
            print(HELP)
            return 0
        elif letter == "v":
            pass
        elif letter == "o":
            if output_format:
                raise FontError(BAD_OPTIONS, "-o: Cannot specify more than one output format.")
            output_format = {"c": "carray", "a": "asmarray", "f": "fontpack", "p": "fontpack",
                             "b": "binary"}.get(value[:1], "")
            if not output_format:
                raise FontError(BAD_OPTIONS, "-o: Unknown output format.")
        elif letter == "Z":
            newline = b"\r\n"
        elif letter == "z":
            newline = b"\n"
        elif letter in "ft":
            if fonts and output_format != "fontpack":
                raise FontError(BAD_OPTIONS, "-f: Cannot have multiple input fonts unless -o fontpack is specified first.")
            if len(fonts) >= MAX_FONTS - 1:
                raise FontError(BAD_OPTIONS, "-f: Too many fonts.")
            current = _read_input(letter, value)
            fonts.append(current)
        elif letter in "abiwscxl":
            _set_metric(current, letter, value)
        else:
            if output_format != "fontpack":
                raise FontError(BAD_OPTIONS, f"-{letter}: Must specify font pack output format.")
            if letter in metadata:
                raise FontError(BAD_OPTIONS, f"-{letter}: Duplicate.")
            encoded = value.encode("utf-8", "surrogateescape")
            if letter == "C" and len(encoded) > 255:
                raise FontError(BAD_OPTIONS, "-C: You don't need such a long copyright string.")
            if letter in _METADATA_LIMITS and len(encoded) >= _METADATA_LIMITS[letter]:
                raise FontError(BAD_OPTIONS, f"-{letter}: Way too long a string!")
            metadata[letter] = encoded
    if not positional:
        raise FontError(BAD_OPTIONS, "Last parameter must be output file name; none was given.")
    if len(positional) > 1:
        raise FontError(BAD_OPTIONS, "Too many trailing parameters.")
    if current is None:
        raise FontError(BAD_OPTIONS, "No input font(s) given. . . . Nothing to do.")
    if not output_format:
        raise FontError(BAD_OPTIONS, "-o: No output format specified.")
    if output_format == "fontpack":
        payload = serialize_fontpack(fonts, metadata)
    elif output_format == "binary":
        payload = serialize_font(current)
    elif output_format == "carray":
        payload = to_c_array(serialize_font(current), newline)
    else:
        payload = to_asm_array(current, newline)
    try:
        Path(positional[0]).write_bytes(payload)
    except OSError as exc:
        raise FontError(BAD_OUTFILE, "Cannot open output file.") from exc
    print(f"Output size: {len(payload)} bytes; conversion finished.")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print("No inputs supplied.\n")
        print(HELP)
        return 0
    try:
        return convert(argv)
    except FontError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code


def run_with_args() -> int:
    return main(sys.argv[1:])


def add_arguments(commands) -> None:
    """Register the subcommand for help text. ``cli.main`` hands its arguments to ``main``."""
    import argparse

    commands.add_parser("convfont", add_help=False, usage=USAGE, description=HELP,
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        help="convert .fnt and text-format fonts to FontLibC data, exactly like CEdev's convfont")
