"""Turn an image into raw pixel data, an AppVar, or a source array.

``-k bin`` gives raw pixels for embedding into the program itself
(``.incbin`` into the classic ``.asm`` / ``.8xp``, or the CEdev Flash App
makefile for the ``.8ek``). ``-k 8xv`` packages the same pixels as an
archived AppVar; ``-k c``, ``asm``, ``ice`` emit source arrays.

Modes: ``rgb565`` (16-bit LE pixels, the default) or ``palette`` (one index
byte per pixel, quantized; the palette is written as a second ``<NAME>_pal``
output, and index 0 is transparency / see-through black).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .convbin import MAX_VAR_SIZE, TYPE_APPVAR, ti_file, to_asm, to_c, to_ice
from .errors import CompileError

OUTPUT_FORMATS = ("bin", "8xv", "c", "asm", "ice")


def _rgb565(red: int, green: int, blue: int) -> int:
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)


def _load_image(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise CompileError(
            "image conversion needs Pillow; install it with: python -m pip install 'tipy-asm[images]'"
        ) from exc
    try:
        with Image.open(path) as handle:
            image = handle.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise CompileError(f"cannot read image {path}: {exc}") from exc
    width, height = image.size
    if not width or not height:
        raise CompileError(f"{path}: image must have nonzero width and height")
    return image, width, height


def convert(image_path: Path, output: Path, oformat: str, name: str,
            mode: str = "rgb565", palette_size: int = 255) -> list[Path]:
    """Convert an image; return the files written."""
    if oformat not in OUTPUT_FORMATS:
        raise CompileError(f"unknown output format '{oformat}'")
    if not 1 <= palette_size <= 255:
        raise CompileError("palette size must be between 1 and 255 (index 0 is transparency)")
    image, width, height = _load_image(image_path)
    pixels = image.load()

    palette: bytes = b""
    if mode == "rgb565":
        data = bytearray()
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = pixels[x, y]
                data += (0 if alpha < 128 else _rgb565(red, green, blue)).to_bytes(2, "little")
    elif mode == "palette":
        reduced = image.convert("RGB").quantize(colors=palette_size, method=2)
        palette_rgb = reduced.getpalette() or []
        palette = b"".join(_rgb565(palette_rgb[i], palette_rgb[i + 1], palette_rgb[i + 2]).to_bytes(2, "little")
                           for i in range(0, 3 * palette_size, 3))
        indices = reduced.load()
        data = bytearray()
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = pixels[x, y]
                data.append(0 if alpha < 128 else indices[x, y] + 1)
    else:
        raise CompileError(f"unknown pixel mode '{mode}' (use rgb565 or palette)")

    if len(data) > MAX_VAR_SIZE:
        raise CompileError(f"image data is {len(data)} bytes, too large for one variable (max {MAX_VAR_SIZE})")

    def payload_as(kind: str, label: str, payload: bytes) -> bytes:
        if kind == "bin":
            return payload
        if kind == "8xv":
            return ti_file(TYPE_APPVAR, label, payload, archived=True)
        return {"c": to_c, "asm": to_asm, "ice": to_ice}[kind](label, payload).encode("ascii")

    def write(label: str, payload: bytes) -> Path:
        suffix = ".bin" if oformat == "bin" else ("." + oformat if oformat != "8xv" else ".8xv")
        target = output.with_name(f"{label}{suffix}")
        target.write_bytes(payload_as(oformat, label, payload))
        return target

    output.parent.mkdir(parents=True, exist_ok=True)
    written = [write(name, bytes(data))]
    if palette:
        written.append(write(f"{name}_pal", palette))
    return written


# ---------------------------------------------------------------- command line
def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add convimg options."""
    parser.add_argument("image", type=Path, help="input image file (PNG, BMP, ...)")
    parser.add_argument("-o", "--output", type=Path, metavar="FILE", help="output file")
    parser.add_argument("-k", "--oformat", default="8xv", metavar="MODE",
                        help="output format: " + ", ".join(OUTPUT_FORMATS) + " (default 8xv)")
    parser.add_argument("-n", "--name", help="AppVar or array/label name (default: output stem)")
    parser.add_argument("-m", "--mode", choices=("rgb565", "palette"), default="rgb565",
                        help="pixel encoding (default rgb565)")
    parser.add_argument("--palette-size", type=int, default=255,
                        help="colors in the palette, excluding transparency (default 255)")


def run(args: argparse.Namespace) -> list[Path]:
    if args.output is None:
        raise CompileError("convimg needs an output file (-o)")
    return convert(args.image, args.output, args.oformat, args.name or args.output.stem,
                   args.mode, args.palette_size)


def run_with_args() -> int:
    import sys
    parser = argparse.ArgumentParser(
        prog="convimg",
        description="Convert an image to an AppVar or C/asm/ICE pixel data (CEdev's convimg)",
    )
    add_arguments(parser)
    try:
        args = parser.parse_args()
        for written in run(args):
            print(f"Wrote {written}")
        return 0
    except Exception as exc:
        print(f"convimg: error: {exc}", file=sys.stderr)
        return 1
