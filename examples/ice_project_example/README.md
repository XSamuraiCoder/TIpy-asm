# ICE Project Example

This is an example ICE (Interactive C for the CE) project that can be converted to TIpy-asm Python format.

## Files

- `main.ice` - Main ICE source file

## Conversion

To convert this ICE project to TIpy-asm Python:

```bash
tipy-asm convert-project examples/ice_project_example -o ice_converted --type ice
```

This will create a `ice_converted` folder with the Python version of the project.

## Original ICE Code

The `main.ice` file demonstrates:
- Graphics initialization with `gfx_Begin()` and `gfx_End()`
- Screen clearing with `gfx_FillScreen()`
- Text drawing with `gfx_PrintStringXY()`
- Keyboard input with `kb_Hit()`
- Pixel drawing with `gfx_DrawPixel()`
- Color setting with `gfx_SetColor()`

## Converted Python Code

After conversion, the code will use the TIpy-asm Python API:
- `graphics.begin()` and `graphics.end()`
- `graphics.fill_screen()`
- `graphics.text()`
- `keyboard.read()`
- `graphics.set_pixel()`
- `graphics.set_color()`
