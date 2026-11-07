"""Convert ICE-style source to TIpy-asm Python. See c_like.py for how.

Statements in this dialect may end at a newline instead of a semicolon.
"""

from __future__ import annotations

from pathlib import Path

from .c_like import Conversion, translate


def convert_ice(source: str | Path) -> Conversion:
    """Translate ICE source, or a Path to an ICE file, returning code and warnings."""
    if isinstance(source, Path):
        source = source.read_text(encoding="utf-8")
    return translate(source, newline_ends_statement=True)


def ice_to_python(source: str | Path) -> str:
    """Translate ICE source, or a Path to an ICE file, to Python source."""
    return convert_ice(source).code


def convert_ice_string(source: str) -> str:
    """Alias for ice_to_python for string input."""
    return ice_to_python(source)
