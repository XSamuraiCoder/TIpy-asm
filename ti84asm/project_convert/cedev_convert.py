"""Convert CEdev C source to TIpy-asm Python. See c_like.py for how."""

from __future__ import annotations

from pathlib import Path

from .c_like import Conversion, translate


def convert_cedev(source: str | Path) -> Conversion:
    """Translate C source, or a Path to a C file, returning code and warnings."""
    if isinstance(source, Path):
        source = source.read_text(encoding="utf-8")
    return translate(source)


def cedev_to_python(source: str | Path) -> str:
    """Translate C source, or a Path to a C file, to Python source."""
    return convert_cedev(source).code


def convert_cedev_string(source: str) -> str:
    """Alias for cedev_to_python for string input."""
    return cedev_to_python(source)
