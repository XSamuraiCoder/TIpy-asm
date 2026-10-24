"""Turn a font into raw ``.fnt`` data, an AppVar, or a source array.

Uses the ``cefont`` package (PyPI: ``XSamurai``) to convert TTF/OTF to
FontLibC data. ``-k bin`` gives raw ``.fnt`` bytes for embedding into the
program itself; ``-k 8xv`` packages them as an archived AppVar; ``-k c``,
``asm``, ``ice`` emit source arrays. An existing ``.fnt`` file can be passed
directly to skip the TTF step.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from .convbin import MAX_VAR_SIZE, TYPE_APPVAR, ti_file, to_asm, to_c, to_ice
from .errors import CompileError

OUTPUT_FORMATS = ("bin", "8xv", "c", "asm", "ice")


def _font_bytes(font: Path, size: int | None) -> bytes:
    """Render a TTF/OTF via cefont, or pass an existing .fnt through."""
    if font.suffix.lower() == ".fnt":
        try:
            return font.read_bytes()
        except OSError as exc:
            raise CompileError(f"cannot read {font}: {exc}") from exc
    if size is None:
        raise CompileError("converting a TTF/OTF needs a pixel size: -s SIZE (or pass a .fnt file)")
    if size <= 0:
        raise CompileError("font size must be a positive pixel height")
    try:
        from cefont import from_ttf
    except ImportError as exc:
        raise CompileError(
            "convfont needs the cefont package; install it with: python -m pip install cefont"
        ) from exc
    try:
        data = from_ttf(str(font), size).to_fnt()
    except Exception as exc:          # cefont raises its own error types
        raise CompileError(f"cannot convert font {font}: {exc}") from exc
    if isinstance(data, str):
        data = data.encode("latin-1")
    return bytes(data)


def convert(font: Path, output: Path, oformat: str, name: str, size: int | None = None) -> Path:
    """Convert a font; return the file written."""
    if oformat not in OUTPUT_FORMATS:
        raise CompileError(f"unknown output format '{oformat}'")
    data = _font_bytes(font, size)
    if len(data) > MAX_VAR_SIZE:
        raise CompileError(f"font data is {len(data)} bytes, too large for one variable (max {MAX_VAR_SIZE})")
    if oformat == "8xv" and not re.fullmatch(r"[A-Za-z0-9]{1,8}", name):
        raise CompileError("on-calc names are 1-8 letters or digits")
    output.parent.mkdir(parents=True, exist_ok=True)
    if oformat == "bin":
        output.write_bytes(data)
    elif oformat == "8xv":
        output.write_bytes(ti_file(TYPE_APPVAR, name, data, archived=True))
    else:
        output.write_text({"c": to_c, "asm": to_asm, "ice": to_ice}[oformat](name, data), encoding="ascii")
    return output


# ---------------------------------------------------------------- command line
def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add convfont options."""
    parser.add_argument("font", type=Path, help="input TTF/OTF font, or an existing .fnt file")
    parser.add_argument("-s", "--size", type=int, metavar="PX",
                        help="font height in pixels (required for TTF/OTF input)")
    parser.add_argument("-o", "--output", type=Path, metavar="FILE", help="output file")
    parser.add_argument("-k", "--oformat", default="8xv", metavar="MODE",
                        help="output format: " + ", ".join(OUTPUT_FORMATS) + " (default 8xv)")
    parser.add_argument("-n", "--name", help="AppVar or array/label name (default: output stem)")


def run(args: argparse.Namespace) -> list[Path]:
    if args.output is None:
        raise CompileError("convfont needs an output file (-o)")
    return [convert(args.font, args.output, args.oformat, args.name or args.output.stem, args.size)]