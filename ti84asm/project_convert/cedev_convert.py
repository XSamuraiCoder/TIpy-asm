"""Convert CEdev C projects to TIpy-asm Python format.

This is a basic converter that handles common CEdev patterns.
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


def cedev_to_python(c_source: str | Path) -> str:
    """Convert CEdev C source code to TIpy-asm Python.
    
    Args:
        c_source: Path to C file or C source string
        
    Returns:
        Python source code as string
    """
    if isinstance(c_source, Path):
        c_source = c_source.read_text(encoding="utf-8")
    
    result = c_source
    
    # ===== PHASE 1: Remove comments and preprocessor directives =====
    result = re.sub(r"//.*", "", result)  # Single-line comments
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)  # Multi-line comments
    result = re.sub(r"#.*", "", result)  # Any line starting with #
    result = re.sub(r"#include\s+[<\"].*[>\"]", "", result)  # Include directives
    result = re.sub(r"#define\s+\w+\s+.*", "", result)  # Define directives
    
    # ===== PHASE 2: Convert CEdev-specific functions first =====
    result = re.sub(r"!os_GetCSC\(\)", "not keyboard.read()", result)
    result = re.sub(r"os_GetCSC\(\)", "keyboard.read()", result)
    result = re.sub(r"gfx_Begin\(\)", "graphics.begin()", result)
    result = re.sub(r"gfx_End\(\)", "graphics.end()", result)
    result = re.sub(r"gfx_FillScreen\((\w+)\)", r"graphics.fill_screen(\1)", result)
    result = re.sub(r"gfx_SetColor\((\w+)\)", r"graphics.set_color(\1)", result)
    # Convert gfx functions - handle both literals and variables
    result = re.sub(r"gfx_FillRectangle\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.fill_rect(\1, \2, \3, \4)", result)
    result = re.sub(r"gfx_DrawRectangle\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.draw_rect(\1, \2, \3, \4)", result)
    result = re.sub(r"gfx_DrawCircle\(([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.circle(\1, \2, \3)", result)
    result = re.sub(r'gfx_PrintStringXY\("([^"]+)",\s*([^,]+),\s*([^)]+)\)', 
                   r'graphics.text("\1", \2, \3)', result)
    result = re.sub(r'gfx_PrintStringXY\("([^"]+)",\s*(\d+),\s*(\d+)\)', 
                   r'graphics.text("\1", \2, \3)', result)
    result = re.sub(r"gfx_DrawPixel\(([^,]+),\s*([^,]+),\s*([^)]+)\)", 
                   r"graphics.set_pixel(\1, \2, \3)", result)
    
    # ===== PHASE 3: Remove type declarations =====
    # Remove type from variable declarations with or without initialization
    # Keep the = sign for initializations
    result = re.sub(
        r"\b(uint8_t|uint16_t|uint24_t|int8_t|int16_t|int24_t|bool|int|byte|word|long|float)\s+(\w+)\s*=",
        r"\2 =",
        result
    )
    result = re.sub(
        r"\b(uint8_t|uint16_t|uint24_t|int8_t|int16_t|int24_t|bool|int|byte|word|long|float)\s+(\w+)\s*;",
        r"\2",
        result
    )
    
    # Remove type from function parameters (use lambda to preserve the punctuation)
    def remove_type_from_param(match):
        return match.group(2) + match.group(3)
    
    result = re.sub(
        r"\b(uint8_t|uint16_t|uint24_t|int8_t|int16_t|int24_t|bool|int|byte|word|long|float)\s+(\w+)\s*([,)])",
        remove_type_from_param,
        result
    )
    
    # ===== PHASE 4: Convert function definitions =====
    # Convert all void func(...) { to def func(...):
    # Use lambda to remove void and any remaining type annotations
    def convert_void_func(match):
        func_name = match.group(1)
        params_str = match.group(2)
        # Remove 'void' from parameter list if present
        params_str = params_str.replace('void', '').strip()
        if not params_str:
            return f"def {func_name}():"
        else:
            return f"def {func_name}({params_str}):"
    
    result = re.sub(r"void\s+(\w+)\s*\(\s*([^)]*)\s*\)\s*\{", convert_void_func, result)
    
    # Also handle void func(void) { separately
    result = re.sub(r"void\s+(\w+)\s*\(\s*void\s*\)\s*\{", r"def \1():", result)
    
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


def convert_cedev_string(c_source: str) -> str:
    """Alias for cedev_to_python for string input."""
    return cedev_to_python(c_source)
