"""Convert ICE source code to TIpy-asm Python format.

This is a basic converter that handles common ICE patterns.
For complex projects, manual adjustments may be needed.
"""

from __future__ import annotations

import re
from pathlib import Path


# Color constant mapping
COLOR_MAP = {
    "gfx_black": "graphics.BLACK",
    "gfx_white": "graphics.WHITE", 
    "gfx_red": "graphics.RED",
    "gfx_green": "graphics.GREEN",
    "gfx_blue": "graphics.BLUE",
    "gfx_yellow": "graphics.YELLOW",
}


def ice_to_python(ice_source: str | Path) -> str:
    """Convert ICE source code to TIpy-asm Python.
    
    Args:
        ice_source: Path to ICE file or ICE source string
        
    Returns:
        Python source code as string
    """
    if isinstance(ice_source, Path):
        ice_source = ice_source.read_text(encoding="utf-8")
    
    result = ice_source
    
    # ===== PHASE 1: Remove comments and preprocessor directives =====
    result = re.sub(r"//.*", "", result)  # Single-line comments
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)  # Multi-line comments
    result = re.sub(r"#.*", "", result)  # Any line starting with #
    
    # ===== PHASE 2: Convert ICE-specific functions first =====
    result = re.sub(r"!kb_Hit\(\)", "not keyboard.read()", result)
    result = re.sub(r"kb_Hit\(\)", "keyboard.read()", result)
    result = re.sub(r"!os_GetCSC\(\)", "not keyboard.read()", result)
    result = re.sub(r"os_GetCSC\(\)", "keyboard.read()", result)
    result = re.sub(r"gfx_Begin\(\)", "graphics.begin()", result)
    result = re.sub(r"gfx_End\(\)", "graphics.end()", result)
    result = re.sub(r"gfx_FillScreen\((\w+)\)", r"graphics.fill_screen(\1)", result)
    result = re.sub(r"gfx_SetColor\((\w+)\)", r"graphics.set_color(\1)", result)
    result = re.sub(r"gfx_FillRectangle\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.fill_rect(\1, \2, \3, \4)", result)
    result = re.sub(r"gfx_DrawRectangle\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.draw_rect(\1, \2, \3, \4)", result)
    result = re.sub(r"gfx_DrawCircle\(([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.circle(\1, \2, \3)", result)
    result = re.sub(r'gfx_PrintStringXY\("([^"]+)",\s*([^,]+),\s*([^)]+)\)', 
                   r'graphics.text("\1", \2, \3)', result)
    result = re.sub(r"gfx_DrawPixel\(([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.set_pixel(\1, \2, \3)", result)
    
    # ===== PHASE 3: Remove type declarations =====
    # Remove type from variable declarations with or without initialization
    result = re.sub(
        r"\b(byte|word|long|float|bool|int)\s+(\w+)\s*=",
        r"\2 =",
        result
    )
    result = re.sub(
        r"\b(byte|word|long|float|bool|int)\s+(\w+)\s*;",
        r"\2",
        result
    )
    
    # Remove type from function parameters (use lambda to preserve the punctuation)
    def remove_type_from_param(match):
        return match.group(2) + match.group(3)
    
    result = re.sub(
        r"\b(byte|word|long|float|bool|int)\s+(\w+)\s*([,)])",
        remove_type_from_param,
        result
    )
    
    # ===== PHASE 4: Convert function definitions =====
    # Convert function definitions: function func() { to def func():
    def convert_function(match):
        func_name = match.group(1)
        params_str = match.group(2)
        # Extract parameter names (skip types)
        params = re.findall(r"\b(?:byte|word|long|float|bool|int|\w+)\s+(\w+)", params_str)
        if params:
            return f"def {func_name}({', '.join(params)}):"
        else:
            return f"def {func_name}():"
    
    result = re.sub(r"function\s+(\w+)\s*\(\s*([^)]*)\s*\)\s*\{", convert_function, result)
    
    # ===== PHASE 5: Remove braces and semicolons =====
    # Remove braces
    result = re.sub(r"\{", "", result)
    result = re.sub(r"\}", "", result)
    
    # Remove all semicolons
    result = re.sub(r";", "", result)
    
    # Convert while loops
    result = re.sub(r"while\s*\(\s*(.*)\s*\)", r"while \1:", result)
    
    # Convert if statements
    result = re.sub(r"if\s*\(\s*(.*)\s*\)", r"if \1:", result)
    
    # Convert for loops (simplified)
    result = re.sub(
        r"for\s*\(\s*(\w+)\s*=\s*(\d+)\s*;\s*(\w+)\s*[<>=!]\s*(\d+)\s*;\s*(\w+)\s*\+\+\s*\)", 
        r"for \1 in range(\2, \4):",
        result
    )
    
    # Convert increment/decrement
    result = re.sub(r"(\w+)\s*\+\+", r"\1 += 1", result)
    result = re.sub(r"(\w+)\s*--", r"\1 -= 1", result)
    
    # ===== PHASE 6: Final cleanup =====
    # Map color constants
    for color, mapped in COLOR_MAP.items():
        result = re.sub(rf"\b{color}\b", mapped, result)
    
    # Fix any remaining gfx_ function calls
    result = re.sub(r"gfx_(\w+)", r"graphics.\1", result)
    
    # Fix any remaining double graphics. references
    result = re.sub(r"graphics\.graphics\.(\w+)", r"graphics.\1", result)
    
    # Clean up empty lines
    lines = [line for line in result.split("\n") if line.strip()]
    result = "\n".join(lines)
    
    # Clean up multiple spaces
    result = re.sub(r"  +", " ", result)
    
    # Add common imports
    if "graphics." in result:
        result = "from ti84 import graphics\n" + result
    if "keyboard." in result:
        result = "from ti84 import keyboard\n" + result
    
    return result


def convert_ice_string(ice_source: str) -> str:
    """Alias for ice_to_python for string input."""
    return ice_to_python(ice_source)
