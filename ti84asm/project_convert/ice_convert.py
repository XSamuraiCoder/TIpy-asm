"""Convert ICE source code to TIpy-asm Python format.

ICE (Interactive C for the CE) has a similar syntax to C but with some
Python-like features. This module converts ICE source to TIpy Python.

Example ICE code:
    #include <gfx.ice>
    
    function main() {
        gfx_FillScreen(gfx_black)
        gfx_PrintStringXY("Hello", 10, 10)
        while (!os_GetCSC())
        gfx_End()
    }

Converts to:
    from ti84 import graphics, keyboard
    
    graphics.begin()
    graphics.fill_screen(graphics.BLACK)
    graphics.text("Hello", 10, 10)
    while not keyboard.read():
        pass
    graphics.end()
"""

from __future__ import annotations

import re
from pathlib import Path

from .cedev_convert import (
    GRAPHX_COLORS,
    GRAPHX_FUNCTIONS,
    KEYPADC_FUNCTIONS,
    FILEIOC_FUNCTIONS,
    FONTLIBC_FUNCTIONS,
    _convert_function_call,
    _convert_color_constant,
    _convert_key_constant,
    _convert_type,
    _convert_constant,
)

# ICE-specific functions
ICE_FUNCTIONS = {
    "gfx_Begin": "graphics.begin",
    "gfx_End": "graphics.end",
    "gfx_FillScreen": "graphics.fill_screen",
    "gfx_PrintStringXY": "graphics.text",
    "gfx_PrintString": "graphics.text",
    "os_GetCSC": "keyboard.read",
    "kb_Hit": "keyboard.read",
}

# ICE-specific syntax patterns
ICE_PATTERNS = {
    # function main() -> def main():
    r"^function\s+(\w+)\s*\(\s*\)": r"def \1():",
    # if (condition) -> if condition:
    r"^\s*if\s*\(\s*([^)]+)\s*\)": r"\1if \2:",
    # while (condition) -> while condition:
    r"^\s*while\s*\(\s*([^)]+)\s*\)": r"\1while \2:",
    # for (var=start; condition; increment) -> for var in range(start, stop, step):
    r"^\s*for\s*\(\s*(\w+)\s*=\s*(\d+)\s*;\s*(\w+)\s*[<>=!]\s*(\d+)\s*;\s*(\w+)\s*\+\+\s*\)": r"\1for \2 in range(\3, \5):",
    # var = value; -> var = value
    r"\b(\w+)\s*=\s*([^;]+);": r"\1 = \2",
    # return; -> return
    r"return;": "return",
    # return value; -> return value
    r"return\s+([^;]+);": r"return \1",
    # break; -> break
    r"break;": "break",
    # continue; -> continue
    r"continue;": "continue",
}

# ICE types
ICE_TYPES = {
    "byte": "int",
    "word": "int",
    "long": "int",
    "float": "float",
    "bool": "bool",
}


def _convert_ice_function(line: str) -> str:
    """Convert ICE-specific function calls."""
    for ice_func, py_func in ICE_FUNCTIONS.items():
        line = re.sub(
            rf"{ice_func}\(" ,
            rf"{py_func}(",
            line
        )
    return line


def _convert_ice_syntax(line: str) -> str:
    """Convert ICE syntax to Python syntax."""
    for pattern, replacement in ICE_PATTERNS.items():
        line = re.sub(pattern, replacement, line)
    return line


def ice_to_python(ice_source: str | Path) -> str:
    """Convert ICE source code to TIpy-asm Python.
    
    Args:
        ice_source: Path to ICE file or ICE source string
        
    Returns:
        Python source code as string
    """
    if isinstance(ice_source, Path):
        ice_source = ice_source.read_text(encoding="utf-8")
    
    lines = ice_source.split("\n")
    python_lines = []
    
    for line in lines:
        # Strip comments
        line = re.sub(r"//.*", "", line)
        line = re.sub(r"\/\*.*\*\/", "", line)
        
        # Skip preprocessor directives
        if line.strip().startswith("#"):
            continue
        
        # Convert ICE types
        line = _convert_type(line)
        
        # Convert ICE-specific types
        for ice_type, py_type in ICE_TYPES.items():
            line = re.sub(rf"\b{ice_type}\b", py_type, line)
        
        # Convert constants
        line = _convert_constant(line)
        line = _convert_color_constant(line)
        line = _convert_key_constant(line)
        
        # Convert ICE function calls
        line = _convert_ice_function(line)
        
        # Convert CEdev function calls (for compatibility)
        line = _convert_function_call(line)
        
        # Convert ICE syntax
        line = _convert_ice_syntax(line)
        
        # Remove braces
        line = line.replace("{", "").replace("}", "")
        
        # Remove semicolons
        line = re.sub(r"\s*;\s*$", "", line)
        
        # Skip empty lines
        if not line.strip():
            continue
        
        # Add to output
        python_lines.append(line)
    
    # Join lines and format
    result = "\n".join(python_lines)
    
    # Add common imports
    if "graphics." in result:
        result = "from ti84 import graphics\n" + result
    if "keyboard." in result:
        result = "from ti84 import keyboard\n" + result
    if "fileioc." in result:
        result = "from ti84 import fileioc\n" + result
    if "font." in result:
        result = "from ti84 import font\n" + result
    
    return result
