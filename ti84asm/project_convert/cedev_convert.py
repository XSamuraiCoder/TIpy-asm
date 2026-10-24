"""Convert CEdev C projects to TIpy-asm Python format.

This module provides conversion for common CEdev patterns:
- Graphics calls (graphx.h)
- File I/O (fileioc.h)
- Keyboard input (keypadc.h)
- Font operations (fontlibc.h)

Example C code:
    #include <graphx.h>
    #include <keypadc.h>
    
    void main(void) {
        gfx_Begin();
        gfx_FillScreen(gfx_black);
        gfx_PrintStringXY("Hello", 10, 10);
        while (!os_GetCSC());
        gfx_End();
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

from ti84asm.errors import CompileError


# CEdev graphx.h color constants to TIpy graphics colors
GRAPHX_COLORS = {
    "gfx_black": "graphics.BLACK",
    "gfx_white": "graphics.WHITE",
    "gfx_red": "graphics.RED",
    "gfx_green": "graphics.GREEN",
    "gfx_blue": "graphics.BLUE",
    "gfx_yellow": "graphics.YELLOW",
    "gfx_cyan": "graphics.CYAN",
    "gfx_magenta": "graphics.MAGENTA",
    "gfx_orange": "graphics.ORANGE",
    "gfx_purple": "graphics.PURPLE",
    "gfx_gray": "graphics.GRAY",
    "gfx_light_gray": "graphics.GRAY",
    "gfx_dark_gray": "graphics.GRAY",
    "gfx_medium_gray": "graphics.GRAY",
}

# CEdev graphx.h functions to TIpy graphics
GRAPHX_FUNCTIONS = {
    "gfx_Begin": "graphics.begin",
    "gfx_End": "graphics.end",
    "gfx_FillScreen": "graphics.fill_screen",
    "gfx_FillRectangle": "graphics.fill_rect",
    "gfx_DrawRectangle": "graphics.rect",
    "gfx_FillCircle": "graphics.fill_circle",
    "gfx_DrawCircle": "graphics.circle",
    "gfx_DrawLine": "graphics.line",
    "gfx_DrawHorizontalLine": "graphics.horiz_line",
    "gfx_DrawVerticalLine": "graphics.vert_line",
    "gfx_DrawPixel": "graphics.pixel",
    "gfx_GetPixel": "graphics.get_pixel",
    "gfx_SetPixel": "graphics.pixel",
    "gfx_PrintString": "graphics.text",
    "gfx_PrintStringXY": "graphics.text",
    "gfx_PrintInt": "graphics.text_int",
    "gfx_PrintUInt": "graphics.text_int",
    "gfx_PrintChar": "graphics.text",
    "gfx_SetColor": "graphics.set_color",
    "gfx_SetTextFGColor": "graphics.set_color",
    "gfx_SetTextBGColor": "# TODO: set bg color",
    "gfx_SetTextTransparentColor": "# TODO: set transparent color",
    "gfx_SetPalette": "# TODO: set palette",
    "gfx_GetStringWidth": "# TODO: string width",
    "gfx_GetCharWidth": "# TODO: char width",
    "gfx_GetTextHeight": "# TODO: text height",
}

# CEdev keypadc.h functions to TIpy keyboard
KEYPADC_FUNCTIONS = {
    "kb_Scan": "keyboard.read",
    "kb_GetKey": "keyboard.read",
    "kb_IsDown": "keyboard.is_down",
    "kb_AnyKey": "# TODO: any key",
}

# CEdev fileioc.h functions to TIpy fileioc
FILEIOC_FUNCTIONS = {
    "file_Open": "fileioc.open",
    "file_Close": "fileioc.close",
    "file_Read": "fileioc.read",
    "file_Write": "fileioc.write",
    "file_Seek": "fileioc.seek",
    "file_Tell": "fileioc.tell",
    "file_GetSize": "fileioc.size",
    "file_Exists": "fileioc.exists",
    "file_Delete": "fileioc.delete",
    "file_Create": "fileioc.create",
    "file_Rename": "fileioc.rename",
}

# CEdev fontlibc.h functions to TIpy font
FONTLIBC_FUNCTIONS = {
    "fontlib_Init": "# TODO: font init",
    "fontlib_SetFont": "# TODO: set font",
    "fontlib_DrawChar": "font.draw_char",
    "fontlib_DrawString": "font.draw_text",
    "fontlib_GetCharWidth": "font.char_width",
    "fontlib_GetStringWidth": "font.string_width",
    "fontlib_GetHeight": "font.height",
    "fontlib_GetBaseline": "font.baseline",
}

# CEdev key codes to TIpy keyboard keys
KEYPADC_KEYS = {
    "kb_KeyUp": "keyboard.UP",
    "kb_KeyDown": "keyboard.DOWN",
    "kb_KeyLeft": "keyboard.LEFT",
    "kb_KeyRight": "keyboard.RIGHT",
    "kb_KeyEnter": "keyboard.ENTER",
    "kb_KeyClear": "keyboard.CLEAR",
    "kb_KeyDel": "keyboard.DEL",
    "kb_KeyAlpha": "keyboard.ALPHA",
    "kb_KeyMode": "keyboard.MODE",
    "kb_Key2nd": "keyboard.SHIFT",
    "kb_KeyStat": "keyboard.STAT",
    "kb_KeyVars": "keyboard.VARS",
    "kb_KeyWindow": "keyboard.WINDOW",
    "kb_KeyZoom": "keyboard.ZOOM",
    "kb_KeyTrace": "keyboard.TRACE",
    "kb_KeyGraph": "keyboard.GRAPH",
}

# Special CEdev types and constants
CEDEV_TYPES = {
    "uint8_t": "int",
    "uint16_t": "int",
    "uint24_t": "int",
    "int8_t": "int",
    "int16_t": "int",
    "int24_t": "int",
    "bool": "bool",
    "true": "True",
    "false": "False",
    "NULL": "None",
}

# CEdev screen dimensions
CEDEV_CONSTANTS = {
    "GFX_LCD_WIDTH": "graphics.width",
    "GFX_LCD_HEIGHT": "graphics.height",
    "gfx_lcd_width": "graphics.width",
    "gfx_lcd_height": "graphics.height",
}


def _convert_function_call(line: str) -> str:
    """Convert a CEdev function call to TIpy Python."""
    # Handle graphx functions
    for c_func, py_func in GRAPHX_FUNCTIONS.items():
        # Handle gfx_PrintStringXY special case (takes x, y)
        if c_func == "gfx_PrintStringXY":
            line = re.sub(
                rf"{c_func}\(([^,]+),\s*(\d+),\s*(\d+)\)",
                rf"{py_func}(\1, {2}, {3})",
                line
            )
        elif c_func == "gfx_PrintString":
            line = re.sub(
                rf"{c_func}\(([^,]+)\)",
                rf"{py_func}(\1, 0, 0)",
                line
            )
        elif c_func in ("gfx_FillRectangle", "gfx_DrawRectangle", "gfx_FillCircle"):
            # These take width/height or radius
            line = re.sub(
                rf"{c_func}\(([^,]+),\s*([^,]+),\s*(\d+),\s*(\d+)\)",
                rf"{py_func}(\1, \2, \3, \4)",
                line
            )
        elif c_func == "gfx_DrawLine":
            line = re.sub(
                rf"{c_func}\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)",
                rf"{py_func}(\1, \2, \3, \4)",
                line
            )
        else:
            # Generic function conversion
            line = re.sub(
                rf"{c_func}\(" ,
                rf"{py_func}(",
                line
            )
    
    # Handle keypadc functions
    for c_func, py_func in KEYPADC_FUNCTIONS.items():
        if c_func == "kb_IsDown":
            # kb_IsDown(group, key) -> keyboard.is_down(key)
            line = re.sub(
                rf"{c_func}\([^,]+,\s*(\w+)\)",
                rf"{py_func}(\1)",
                line
            )
        else:
            line = re.sub(
                rf"{c_func}\(" ,
                rf"{py_func}(",
                line
            )
    
    # Handle fileioc functions
    for c_func, py_func in FILEIOC_FUNCTIONS.items():
        line = re.sub(
            rf"{c_func}\(" ,
            rf"{py_func}(",
            line
        )
    
    # Handle fontlibc functions
    for c_func, py_func in FONTLIBC_FUNCTIONS.items():
        line = re.sub(
            rf"{c_func}\(" ,
            rf"{py_func}(",
            line
        )
    
    return line


def _convert_color_constant(line: str) -> str:
    """Convert CEdev color constants to TIpy graphics colors."""
    for c_color, py_color in GRAPHX_COLORS.items():
        line = re.sub(rf"\b{c_color}\b", py_color, line)
    return line


def _convert_key_constant(line: str) -> str:
    """Convert CEdev key constants to TIpy keyboard keys."""
    for c_key, py_key in KEYPADC_KEYS.items():
        line = re.sub(rf"\b{c_key}\b", py_key, line)
    return line


def _convert_type(line: str) -> str:
    """Convert CEdev types to Python types."""
    for c_type, py_type in CEDEV_TYPES.items():
        line = re.sub(rf"\b{c_type}\b", py_type, line)
    return line


def _convert_constant(line: str) -> str:
    """Convert CEdev constants to TIpy constants."""
    for c_const, py_const in CEDEV_CONSTANTS.items():
        line = re.sub(rf"\b{c_const}\b", py_const, line)
    return line


def _clean_c_declarations(line: str) -> str:
    """Remove C-specific declarations and syntax."""
    # Remove variable declarations
    line = re.sub(r"\b(uint8_t|uint16_t|uint24_t|int8_t|int16_t|int24_t|bool)\s+\w+\s*;", "", line)
    line = re.sub(r"\b\(\*\w+\)\([^)]*\)\s*;", "", line)
    
    # Remove #include lines
    line = re.sub(r"#include\s+[<\"].*[>\"]", "", line)
    
    # Remove #define lines
    line = re.sub(r"#define\s+\w+\s+.*", "", line)
    
    # Remove type casts
    line = re.sub(r"\(\w+\)", "", line)
    
    # Remove semicolons
    line = re.sub(r";", "", line)
    
    # Remove C-style comments
    line = re.sub(r"//.*", "", line)
    line = re.sub(r"/\*.*\*/", "", line)
    
    # Remove void return type
    line = re.sub(r"\bvoid\s+", "", line)
    
    return line


def cedev_to_python(c_source: str | Path) -> str:
    """Convert CEdev C source code to TIpy-asm Python.
    
    Args:
        c_source: Path to C file or C source string
        
    Returns:
        Python source code as string
    """
    if isinstance(c_source, Path):
        c_source = c_source.read_text(encoding="utf-8")
    
    lines = c_source.split("\n")
    python_lines = []
    
    # Track state
    in_function = False
    brace_depth = 0
    skip_until_closing_brace = False
    
    for line in lines:
        # Strip comments
        line = re.sub(r"//.*", "", line)
        line = re.sub(r"\/\*.*\*\/", "", line)
        
        # Skip preprocessor directives
        if line.strip().startswith("#"):
            if line.strip().startswith("#include") or line.strip().startswith("#define"):
                continue
        
        # Handle braces
        open_braces = line.count("{")
        close_braces = line.count("}")
        
        # Remove braces
        line = line.replace("{", "").replace("}", "")
        
        # Convert types
        line = _convert_type(line)
        
        # Convert constants
        line = _convert_constant(line)
        line = _convert_color_constant(line)
        line = _convert_key_constant(line)
        
        # Convert function calls
        line = _convert_function_call(line)
        
        # Clean C declarations
        line = _clean_c_declarations(line)
        
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
