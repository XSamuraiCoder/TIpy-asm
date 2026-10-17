"""TI-84 Plus CE built-in Flash App libraries.

The Python compiler owns these routines and emits them into each app. The
runtime talks to the calculator OS/framebuffer directly and needs no clibs,
GraphX, keypadc, or fileioc runtime libraries.

LIBRARY_C is the single table the Flash App compiler uses to type-check and
lower library calls. Each entry is ``name: (template, params, return)``:

* ``template`` is a C function name (called with the arguments) or, when it
  starts with ``=``, a ``str.format`` template using ``{0}``, ``{1}``...
* ``params`` is a list of ``(name, kind, default)``; kinds are ``i`` integer,
  ``s`` string, ``n`` AppVar-name literal. ``default`` of None means required.
* ``return`` is ``v`` (nothing), ``i`` (integer) or ``b`` (bool).
"""

from ti84libs.graphics import COLORS as RGB565_COLORS
from ti84libs.graph import GRAPH_API
from ti84libs.keyboard import KEYS as KEYBOARD_KEYS

_X, _Y, _C = ("x", "i", None), ("y", "i", None), ("color", "i", -1)


def _p(*names, color=True):
    params = [(n, "i", None) for n in names]
    return params + ([_C] if color else [])


LIBRARY_C = {
    "ti84.graphics": {
        "begin": ("ti84py_gfx_begin", [], "v"),
        "set_color": ("ti84py_gfx_set_color", _p("color", color=False), "i"),
        "clear": ("ti84py_gfx_clear", [], "v"),
        "fill_screen": ("ti84py_gfx_fill_screen", [_C], "v"),
        "pixel": ("ti84py_gfx_pixel", _p("x", "y"), "v"),
        "get_pixel": ("ti84py_gfx_get_pixel", _p("x", "y", color=False), "i"),
        "line": ("ti84py_gfx_line", _p("x1", "y1", "x2", "y2"), "v"),
        "rect": ("ti84py_gfx_rect", _p("x", "y", "width", "height"), "v"),
        "rectangle": ("=ti84py_gfx_rect({0}, {1}, ({2}) - 1, ({3}) - 1, {4})", _p("x", "y", "width", "height"), "v"),
        "fill_rect": ("ti84py_gfx_fill_rect", _p("x", "y", "width", "height"), "v"),
        "fill_rectangle": ("ti84py_gfx_fill_rect", _p("x", "y", "width", "height"), "v"),
        "triangle": ("ti84py_gfx_triangle", _p("x1", "y1", "x2", "y2", "x3", "y3"), "v"),
        "circle": ("ti84py_gfx_circle", _p("x", "y", "radius"), "v"),
        "fill_circle": ("ti84py_gfx_fill_circle", _p("x", "y", "radius"), "v"),
        "horiz_line": ("=ti84py_gfx_fill_rect({0}, {1}, {2}, 1, {3})", _p("x", "y", "length"), "v"),
        "vert_line": ("=ti84py_gfx_fill_rect({0}, {1}, 1, {2}, {3})", _p("x", "y", "length"), "v"),
        "text": ("ti84py_gfx_text", [("string", "s", None), _X, _Y], "v"),
        "text_int": ("ti84py_gfx_text_int", _p("value", "x", "y", color=False), "v"),
        "wait_key": ("ti84py_wait_key", [], "v"),
        "save_cursor": ("ti84py_gfx_save_cursor", _p("x", "y", color=False), "v"),
        "restore_cursor": ("ti84py_gfx_restore_cursor", [], "v"),
        "width": ("=320", [], "i"),
        "height": ("=240", [], "i"),
    },
    "ti84.keyboard": {
        "read": ("ti84py_read_key", [], "i"),
        "get": ("=(int32_t)os_GetCSC()", [], "i"),
        "is_down": ("ti84py_kb_is_down", _p("key", color=False), "b"),
    },
    "ti84.storage": {
        "create": ("ti84py_storage_create", [("name", "n", None), ("size", "i", None)], "v"),
        "read_byte": ("ti84py_storage_read_byte", [("name", "n", None), ("offset", "i", None)], "i"),
        "write_byte": ("ti84py_storage_write_byte", [("name", "n", None), ("offset", "i", None), ("value", "i", None)], "v"),
    },
    "ti84.file": {
        "exists": ("ti84py_file_exists", [("name", "n", None)], "b"),
        "size": ("ti84py_file_size", [("name", "n", None)], "i"),
        "create": ("ti84py_storage_create", [("name", "n", None), ("size", "i", None)], "v"),
        "delete": ("ti84py_file_delete", [("name", "n", None)], "v"),
        "clear": ("ti84py_file_clear", [("name", "n", None)], "v"),
        "read_byte": ("ti84py_storage_read_byte", [("name", "n", None), ("offset", "i", None)], "i"),
        "write_byte": ("ti84py_storage_write_byte", [("name", "n", None), ("offset", "i", None), ("value", "i", None)], "v"),
        "read_u16": ("ti84py_file_read_u16", [("name", "n", None), ("offset", "i", None)], "i"),
        "write_u16": ("ti84py_file_write_u16", [("name", "n", None), ("offset", "i", None), ("value", "i", None)], "v"),
    },
    "ti84.math": {
        "abs": ("ti84py_math_abs", _p("value", color=False), "i"),
        "min": ("ti84py_math_min", _p("a", "b", color=False), "i"),
        "max": ("ti84py_math_max", _p("a", "b", color=False), "i"),
        "clamp": ("ti84py_math_clamp", _p("value", "low", "high", color=False), "i"),
        "sqrt": ("ti84py_math_sqrt", _p("value", color=False), "i"),
        "pow": ("ti84py_pow", _p("base", "exponent", color=False), "i"),
        "sign": ("ti84py_math_sign", _p("value", color=False), "i"),
        "sin": ("ti84py_math_sin", _p("degrees", color=False), "i"),
        "cos": ("ti84py_math_cos", _p("degrees", color=False), "i"),
    },
    "ti84.random": {
        "seed": ("ti84py_random_seed", _p("seed", color=False), "v"),
        "randrange": ("ti84py_random_range", _p("limit", color=False), "i"),
        "randint": ("ti84py_random_between", _p("low", "high", color=False), "i"),
    },
    "ti84.graph": {
        name: (f"=ti84py_graph_{name}()", [], "v")
        for name in GRAPH_API
    },
}

# Back-compat arity table: module -> name -> (min args, max args).
LIBRARY_API = {
    module: {
        name: (sum(1 for p in params if p[2] is None), len(params))
        for name, (_t, params, _r) in functions.items()
    }
    for module, functions in LIBRARY_C.items()
}


def supported_call(module: str, name: str, count: int) -> bool:
    arity = LIBRARY_API.get(module, {}).get(name)
    return arity is not None and arity[0] <= count <= arity[1]


RUNTIME_C = r'''/* Generated from TIpy's Python CE built-in library definitions. */
#include <stdint.h>
#include <ti/vars.h>
#include <ti/screen.h>
#include <ti/getcsc.h>

#ifndef TI84PY_VRAM_ADDR
#define TI84PY_VRAM_ADDR 0xD40000
#endif
static volatile uint16_t * const ti84py_vram = (volatile uint16_t*)TI84PY_VRAM_ADDR;
#if TI84PY_GRAPH_ENABLED
static uint8_t ti84py_buffer[320u * 240u];
#endif
static uint8_t ti84py_draw_buffer = 0;
static int32_t ti84py_text_row = 0;
static int32_t ti84py_color = 0;
static uint16_t ti84py_cursor_underlay[12u * 16u];
static int32_t ti84py_cursor_x, ti84py_cursor_y, ti84py_cursor_w, ti84py_cursor_h;
static uint8_t ti84py_cursor_saved = 0;
static void ti84py_gfx_begin(void)
{
    volatile uint8_t *lcd_ctrl = (volatile uint8_t*)0xF60018;
    *lcd_ctrl = (uint8_t)((*lcd_ctrl & 0x0F) | 0xC0);
    ((void (*)(void))0x021E1C)();
    os_SetDrawFGColor(0);
    ti84py_draw_buffer = 0;
}
#if TI84PY_GRAPH_ENABLED
static uint8_t ti84py_rgb565_index(uint16_t color)
{
    uint8_t r = (uint8_t)((color >> 13) & 7u);
    uint8_t g = (uint8_t)((color >> 8) & 7u);
    uint8_t b = (uint8_t)((color >> 3) & 3u);
    return (uint8_t)((r << 5) | (g << 2) | b);
}
static uint16_t ti84py_index_rgb565(uint8_t index)
{
    return ti84py_rgb565_palette[index];
}
#endif
static int32_t ti84py_gfx_set_color(int32_t color)
{
    int32_t old = ti84py_color;
    ti84py_color = color & 0xFFFF;
    return old;
}
static void ti84py_gfx_pixel(int32_t x, int32_t y, int32_t color)
{
    uint32_t offset;
    if ((uint32_t)x >= 320u || (uint32_t)y >= 240u) return;
    offset = (uint32_t)y * 320u + (uint32_t)x;
    if (color < 0) color = ti84py_color;
#if TI84PY_GRAPH_ENABLED
    if (ti84py_draw_buffer) { ti84py_buffer[offset] = ti84py_rgb565_index((uint16_t)color); return; }
#endif
    ti84py_vram[offset] = (uint16_t)color;
}
static void ti84py_gfx_fill_rect(int32_t x, int32_t y, int32_t w, int32_t h, int32_t color)
{
    int32_t x0 = x < 0 ? 0 : x, y0 = y < 0 ? 0 : y;
    int32_t x1 = x + w, y1 = y + h, row;
    volatile uint16_t *row_ptr;
    if (color < 0) color = ti84py_color;
    if (x1 > 320) x1 = 320;
    if (y1 > 240) y1 = 240;
    if (w <= 0 || h <= 0 || x0 >= x1 || y0 >= y1) return;
#if TI84PY_GRAPH_ENABLED
    if (ti84py_draw_buffer) {
        uint8_t value = ti84py_rgb565_index((uint16_t)color);
        uint8_t *buffer_row = ti84py_buffer + (uint32_t)y0 * 320u + (uint32_t)x0;
        for (row = y0; row < y1; ++row) {
            uint8_t *pixel = buffer_row;
            uint8_t *end = pixel + (x1 - x0);
            while (pixel + 4 <= end) {
                pixel[0] = value; pixel[1] = value;
                pixel[2] = value; pixel[3] = value;
                pixel += 4;
            }
            while (pixel < end) *pixel++ = value;
            buffer_row += 320;
        }
        return;
    }
#endif
    row_ptr = ti84py_vram + (uint32_t)y0 * 320u + (uint32_t)x0;
    for (row = y0; row < y1; ++row) {
        volatile uint16_t *pixel = row_ptr;
        int32_t remaining = x1 - x0;
        while (remaining >= 4) {
            pixel[0] = (uint16_t)color; pixel[1] = (uint16_t)color;
            pixel[2] = (uint16_t)color; pixel[3] = (uint16_t)color;
            pixel += 4;
            remaining -= 4;
        }
        while (remaining-- > 0) *pixel++ = (uint16_t)color;
        row_ptr += 320;
    }
}
static void ti84py_gfx_line(int32_t x0, int32_t y0, int32_t x1, int32_t y1, int32_t color)
{
    int32_t dx = x1 >= x0 ? x1 - x0 : x0 - x1;
    int32_t sx = x0 < x1 ? 1 : -1;
    int32_t dy0 = y1 >= y0 ? y1 - y0 : y0 - y1;
    int32_t dy = -dy0, sy = y0 < y1 ? 1 : -1, err = dx + dy;
    for (;;) {
        int32_t e2;
        ti84py_gfx_pixel(x0, y0, color);
        if (x0 == x1 && y0 == y1) break;
        e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}
static void ti84py_gfx_rect(int32_t x, int32_t y, int32_t w, int32_t h, int32_t color)
{
    ti84py_gfx_line(x, y, x + w, y, color);
    ti84py_gfx_line(x + w, y, x + w, y + h, color);
    ti84py_gfx_line(x + w, y + h, x, y + h, color);
    ti84py_gfx_line(x, y + h, x, y, color);
}
static int32_t ti84py_edge_x(int32_t ax, int32_t ay, int32_t bx, int32_t by, int32_t y)
{
    return ax + (y - ay) * (bx - ax) / (by - ay);
}
static void ti84py_gfx_triangle(int32_t x0, int32_t y0, int32_t x1, int32_t y1,
                                int32_t x2, int32_t y2, int32_t color)
{
    int32_t y, miny = y0 < y1 ? (y0 < y2 ? y0 : y2) : (y1 < y2 ? y1 : y2);
    int32_t maxy = y0 > y1 ? (y0 > y2 ? y0 : y2) : (y1 > y2 ? y1 : y2);
    if (miny < 0) miny = 0;
    if (maxy > 239) maxy = 239;
    for (y = miny; y <= maxy; ++y) {
        int32_t xx[3], n = 0, i, left, right;
        if (y0 == y1) { if (y == y0) { xx[n++] = x0; xx[n++] = x1; } }
        else if (y >= (y0 < y1 ? y0 : y1) && y <= (y0 > y1 ? y0 : y1)) xx[n++] = ti84py_edge_x(x0,y0,x1,y1,y);
        if (y1 == y2) { if (y == y1) { xx[n++] = x1; xx[n++] = x2; } }
        else if (y >= (y1 < y2 ? y1 : y2) && y <= (y1 > y2 ? y1 : y2)) xx[n++] = ti84py_edge_x(x1,y1,x2,y2,y);
        if (y2 == y0) { if (y == y2) { xx[n++] = x2; xx[n++] = x0; } }
        else if (y >= (y2 < y0 ? y2 : y0) && y <= (y2 > y0 ? y2 : y0)) xx[n++] = ti84py_edge_x(x2,y2,x0,y0,y);
        if (n < 2) continue;
        left = right = xx[0];
        for (i = 1; i < n; ++i) { if (xx[i] < left) left = xx[i]; if (xx[i] > right) right = xx[i]; }
        ti84py_gfx_fill_rect(left, y, right - left + 1, 1, color);
    }
}
static void ti84py_gfx_circle(int32_t cx, int32_t cy, int32_t radius, int32_t color)
{
    int32_t x = radius, y = 0, err = 1 - radius;
    while (x >= y) {
        ti84py_gfx_pixel(cx+x,cy+y,color); ti84py_gfx_pixel(cx+y,cy+x,color);
        ti84py_gfx_pixel(cx-y,cy+x,color); ti84py_gfx_pixel(cx-x,cy+y,color);
        ti84py_gfx_pixel(cx-x,cy-y,color); ti84py_gfx_pixel(cx-y,cy-x,color);
        ti84py_gfx_pixel(cx+y,cy-x,color); ti84py_gfx_pixel(cx+x,cy-y,color);
        ++y;
        if (err < 0) err += 2*y+1;
        else { --x; err += 2*(y-x)+1; }
    }
}
static void ti84py_gfx_fill_circle(int32_t cx, int32_t cy, int32_t radius, int32_t color)
{
    int32_t x = radius, y = 0, err = 1 - radius;
    if (radius < 0) return;
    while (x >= y) {
        ti84py_gfx_fill_rect(cx - x, cy + y, 2 * x + 1, 1, color);
        ti84py_gfx_fill_rect(cx - x, cy - y, 2 * x + 1, 1, color);
        ti84py_gfx_fill_rect(cx - y, cy + x, 2 * y + 1, 1, color);
        ti84py_gfx_fill_rect(cx - y, cy - x, 2 * y + 1, 1, color);
        ++y;
        if (err < 0) err += 2 * y + 1;
        else { --x; err += 2 * (y - x) + 1; }
    }
}
static void ti84py_gfx_clear(void)
{
    ti84py_gfx_fill_rect(0, 0, 320, 240, 0xFFFF);
    ti84py_text_row = 0;
}
static void ti84py_gfx_fill_screen(int32_t color)
{
    ti84py_gfx_fill_rect(0, 0, 320, 240, color);
}
static void ti84py_gfx_save_cursor(int32_t x, int32_t y)
{
    int32_t row, col;
    ti84py_cursor_x = x < 0 ? 0 : x;
    ti84py_cursor_y = y < 0 ? 0 : y;
    ti84py_cursor_w = x < 0 ? 12 + x : 12;
    ti84py_cursor_h = y < 0 ? 16 + y : 16;
    if (ti84py_cursor_x + ti84py_cursor_w > 320) ti84py_cursor_w = 320 - ti84py_cursor_x;
    if (ti84py_cursor_y + ti84py_cursor_h > 240) ti84py_cursor_h = 240 - ti84py_cursor_y;
    if (ti84py_cursor_w <= 0 || ti84py_cursor_h <= 0) { ti84py_cursor_saved = 0; return; }
    for (row = 0; row < ti84py_cursor_h; ++row) {
        volatile uint16_t *src = ti84py_vram + (uint32_t)(ti84py_cursor_y + row) * 320u + (uint32_t)ti84py_cursor_x;
        uint16_t *dst = ti84py_cursor_underlay + row * 12;
        for (col = 0; col < ti84py_cursor_w; ++col) dst[col] = src[col];
    }
    ti84py_cursor_saved = 1;
}
static void ti84py_gfx_restore_cursor(void)
{
    int32_t row, col;
    if (!ti84py_cursor_saved) return;
    for (row = 0; row < ti84py_cursor_h; ++row) {
        volatile uint16_t *dst = ti84py_vram + (uint32_t)(ti84py_cursor_y + row) * 320u + (uint32_t)ti84py_cursor_x;
        const uint16_t *src = ti84py_cursor_underlay + row * 12;
        for (col = 0; col < ti84py_cursor_w; ++col) dst[col] = src[col];
    }
    ti84py_cursor_saved = 0;
}
#if TI84PY_GRAPH_ENABLED
static void ti84py_graph_set_draw_buffer(void)
{
    ti84py_draw_buffer = 1;
}
static void ti84py_graph_set_draw_screen(void)
{
    ti84py_draw_buffer = 0;
}
static void ti84py_graph_blit_buffer(void)
{
    uint32_t i;
    for (i = 0; i < 320u * 240u; ++i) ti84py_vram[i] = ti84py_index_rgb565(ti84py_buffer[i]);
}
static void ti84py_graph_blit_screen(void)
{
    uint32_t i;
    for (i = 0; i < 320u * 240u; ++i) ti84py_buffer[i] = ti84py_rgb565_index(ti84py_vram[i]);
}
static void ti84py_graph_swap_draw(void)
{
    ti84py_graph_blit_buffer();
}
static void ti84py_graph_begin(void)
{
    ti84py_gfx_begin();
}
static void ti84py_graph_end(void)
{
    ti84py_draw_buffer = 0;
    ((void (*)(void))0x021E1C)();
}
#endif
static void ti84py_gfx_text(const char *s, int32_t x, int32_t y)
{
    if (x >= 0 && y >= 0 && x < 320 && y < 240)
        (void)os_FontDrawText(s, (uint16_t)(x / 6), (uint8_t)(y / 8));
}
static int32_t ti84py_read_key(void)
{
    int32_t key;
    do { key = os_GetCSC(); } while (key != 0);
    do { key = os_GetCSC(); } while (key == 0);
    return key;
}
static void ti84py_storage_create(const char *name, int32_t size)
{
    int archived = 0; var_t *var = os_GetAppVarData(name, &archived); uint32_t i;
    if (var || size < 1 || size > 65535) return;
    var = os_CreateAppVar(name, (uint16_t)size);
    if (!var) return;
    for (i = 0; i < (uint32_t)size; ++i) var->data[i] = 0;
}
static int32_t ti84py_storage_read_byte(const char *name, int32_t offset)
{
    var_t *var = os_GetAppVarData(name, 0);
    if (!var || offset < 0 || (uint32_t)offset >= var->size) return 0;
    return var->data[offset];
}
static int32_t ti84py_file_exists(const char *name)
{
    return os_GetAppVarData(name, 0) != 0;
}
static int32_t ti84py_file_size(const char *name)
{
    var_t *var = os_GetAppVarData(name, 0);
    return var ? (int32_t)var->size : 0;
}
static int32_t ti84py_file_read_u16(const char *name, int32_t offset)
{
    var_t *var = os_GetAppVarData(name, 0);
    if (!var || offset < 0 || (uint32_t)offset + 1u >= var->size) return 0;
    return (int32_t)((uint16_t)var->data[offset] | ((uint16_t)var->data[offset + 1] << 8));
}
static void ti84py_file_write_u16(const char *name, int32_t offset, int32_t value)
{
    int archived = 0;
    var_t *var = os_GetAppVarData(name, &archived);
    if (!var || archived || offset < 0 || (uint32_t)offset + 1u >= var->size || value < 0 || value > 65535) return;
    var->data[offset] = (uint8_t)value;
    var->data[offset + 1] = (uint8_t)((uint32_t)value >> 8);
}
static void ti84py_file_delete(const char *name)
{
    int archived = 0;
    if (os_GetAppVarData(name, &archived) && !archived) os_DelAppVar(name);
}
static void ti84py_file_clear(const char *name)
{
    int archived = 0;
    var_t *var = os_GetAppVarData(name, &archived);
    uint32_t i;
    if (!var || archived) return;
    for (i = 0; i < var->size; ++i) var->data[i] = 0;
}
static void ti84py_storage_write_byte(const char *name, int32_t offset, int32_t value)
{
    int archived = 0; var_t *var = os_GetAppVarData(name, &archived);
    if (!var || archived || offset < 0 || (uint32_t)offset >= var->size || value < 0 || value > 255) return;
    var->data[offset] = (uint8_t)value;
}
static int32_t ti84py_math_abs(int32_t value) { return value < 0 ? -value : value; }
static int32_t ti84py_math_min(int32_t a, int32_t b) { return a < b ? a : b; }
static int32_t ti84py_math_max(int32_t a, int32_t b) { return a > b ? a : b; }
static int32_t ti84py_math_clamp(int32_t value, int32_t low, int32_t high)
{
    return value < low ? low : (value > high ? high : value);
}
static int32_t ti84py_math_sqrt(int32_t value)
{
    uint32_t n, bit = (uint32_t)1 << 30, result = 0;   /* int is 24-bit on eZ80 */
    if (value <= 0) return 0;
    n = (uint32_t)value;
    while (bit > n) bit >>= 2;
    while (bit) {
        if (n >= result + bit) { n -= result + bit; result = (result >> 1) + bit; }
        else result >>= 1;
        bit >>= 2;
    }
    return (int32_t)result;
}
static uint16_t ti84py_random_state = 0xACE1u;
static void ti84py_random_seed(int32_t seed) { ti84py_random_state = seed ? (uint16_t)seed : 0xACE1u; }
static int32_t ti84py_random_range(int32_t limit)
{
    uint16_t x = ti84py_random_state;
    if (limit <= 0) return 0;
    x ^= (uint16_t)(x << 7); x ^= (uint16_t)(x >> 9); x ^= (uint16_t)(x << 8);
    ti84py_random_state = x ? x : 0xACE1u;
    return limit >= 65536 ? (int32_t)x : (int32_t)(x % (uint16_t)limit);
}

'''


RUNTIME_EXTRA_C = r'''
/* ---- Python language support: lists, strings, integer semantics, print ---- */
typedef struct { int32_t *data; int32_t len; } ti84py_list;
static ti84py_list ti84py_mklist(int32_t *buf, int32_t n, const int32_t *src)
{
    ti84py_list l; int32_t i;
    for (i = 0; i < n; ++i) buf[i] = src[i];
    l.data = buf; l.len = n;
    return l;
}
static ti84py_list ti84py_mkfill(int32_t *buf, int32_t n, int32_t value)
{
    ti84py_list l; int32_t i;
    for (i = 0; i < n; ++i) buf[i] = value;
    l.data = buf; l.len = n;
    return l;
}
static int32_t ti84py_list_get(ti84py_list l, int32_t i)
{
    if (i < 0) i += l.len;
    return (i < 0 || i >= l.len) ? 0 : l.data[i];
}
static void ti84py_list_set(ti84py_list l, int32_t i, int32_t value)
{
    if (i < 0) i += l.len;
    if (i >= 0 && i < l.len) l.data[i] = value;
}
static int32_t ti84py_list_contains(ti84py_list l, int32_t value)
{
    int32_t i;
    for (i = 0; i < l.len; ++i) if (l.data[i] == value) return 1;
    return 0;
}
static int32_t ti84py_list_sum(ti84py_list l)
{
    int32_t i, total = 0;
    for (i = 0; i < l.len; ++i) total += l.data[i];
    return total;
}
static int32_t ti84py_list_min(ti84py_list l)
{
    int32_t i, best = l.len ? l.data[0] : 0;
    for (i = 1; i < l.len; ++i) if (l.data[i] < best) best = l.data[i];
    return best;
}
static int32_t ti84py_list_max(ti84py_list l)
{
    int32_t i, best = l.len ? l.data[0] : 0;
    for (i = 1; i < l.len; ++i) if (l.data[i] > best) best = l.data[i];
    return best;
}
static int32_t ti84py_strlen(const char *s)
{
    int32_t n = 0;
    while (s[n]) ++n;
    return n;
}
static int32_t ti84py_str_at(const char *s, int32_t i)
{
    int32_t n = ti84py_strlen(s);
    if (i < 0) i += n;
    return (i < 0 || i >= n) ? 0 : (int32_t)(uint8_t)s[i];
}
static const char ti84py_char_table[512] = {0, 0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0, 8, 0, 9, 0, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 15, 0, 16, 0, 17, 0, 18, 0, 19, 0, 20, 0, 21, 0, 22, 0, 23, 0, 24, 0, 25, 0, 26, 0, 27, 0, 28, 0, 29, 0, 30, 0, 31, 0, 32, 0, 33, 0, 34, 0, 35, 0, 36, 0, 37, 0, 38, 0, 39, 0, 40, 0, 41, 0, 42, 0, 43, 0, 44, 0, 45, 0, 46, 0, 47, 0, 48, 0, 49, 0, 50, 0, 51, 0, 52, 0, 53, 0, 54, 0, 55, 0, 56, 0, 57, 0, 58, 0, 59, 0, 60, 0, 61, 0, 62, 0, 63, 0, 64, 0, 65, 0, 66, 0, 67, 0, 68, 0, 69, 0, 70, 0, 71, 0, 72, 0, 73, 0, 74, 0, 75, 0, 76, 0, 77, 0, 78, 0, 79, 0, 80, 0, 81, 0, 82, 0, 83, 0, 84, 0, 85, 0, 86, 0, 87, 0, 88, 0, 89, 0, 90, 0, 91, 0, 92, 0, 93, 0, 94, 0, 95, 0, 96, 0, 97, 0, 98, 0, 99, 0, 100, 0, 101, 0, 102, 0, 103, 0, 104, 0, 105, 0, 106, 0, 107, 0, 108, 0, 109, 0, 110, 0, 111, 0, 112, 0, 113, 0, 114, 0, 115, 0, 116, 0, 117, 0, 118, 0, 119, 0, 120, 0, 121, 0, 122, 0, 123, 0, 124, 0, 125, 0, 126, 0, 127, 0, 128, 0, 129, 0, 130, 0, 131, 0, 132, 0, 133, 0, 134, 0, 135, 0, 136, 0, 137, 0, 138, 0, 139, 0, 140, 0, 141, 0, 142, 0, 143, 0, 144, 0, 145, 0, 146, 0, 147, 0, 148, 0, 149, 0, 150, 0, 151, 0, 152, 0, 153, 0, 154, 0, 155, 0, 156, 0, 157, 0, 158, 0, 159, 0, 160, 0, 161, 0, 162, 0, 163, 0, 164, 0, 165, 0, 166, 0, 167, 0, 168, 0, 169, 0, 170, 0, 171, 0, 172, 0, 173, 0, 174, 0, 175, 0, 176, 0, 177, 0, 178, 0, 179, 0, 180, 0, 181, 0, 182, 0, 183, 0, 184, 0, 185, 0, 186, 0, 187, 0, 188, 0, 189, 0, 190, 0, 191, 0, 192, 0, 193, 0, 194, 0, 195, 0, 196, 0, 197, 0, 198, 0, 199, 0, 200, 0, 201, 0, 202, 0, 203, 0, 204, 0, 205, 0, 206, 0, 207, 0, 208, 0, 209, 0, 210, 0, 211, 0, 212, 0, 213, 0, 214, 0, 215, 0, 216, 0, 217, 0, 218, 0, 219, 0, 220, 0, 221, 0, 222, 0, 223, 0, 224, 0, 225, 0, 226, 0, 227, 0, 228, 0, 229, 0, 230, 0, 231, 0, 232, 0, 233, 0, 234, 0, 235, 0, 236, 0, 237, 0, 238, 0, 239, 0, 240, 0, 241, 0, 242, 0, 243, 0, 244, 0, 245, 0, 246, 0, 247, 0, 248, 0, 249, 0, 250, 0, 251, 0, 252, 0, 253, 0, 254, 0, 255, 0};
static const char *ti84py_str_char(const char *s, int32_t i)
{
    int32_t n = ti84py_strlen(s);
    if (i < 0) i += n;
    return (i < 0 || i >= n) ? ti84py_char_table : ti84py_char_table + 2 * (uint8_t)s[i];
}
static int32_t ti84py_streq(const char *a, const char *b)
{
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}
static int32_t ti84py_floordiv(int32_t a, int32_t b)
{
    int32_t q;
    if (b == 0) return 0;
    q = a / b;
    if ((a % b) != 0 && ((a < 0) != (b < 0))) --q;
    return q;
}
static int32_t ti84py_mod(int32_t a, int32_t b)
{
    int32_t r;
    if (b == 0) return 0;
    r = a % b;
    if (r != 0 && ((r < 0) != (b < 0))) r += b;
    return r;
}
static int32_t ti84py_shl(int32_t a, int32_t b)
{
    return (b < 0 || b >= 32) ? 0 : (int32_t)((uint32_t)a << b);
}
static int32_t ti84py_shr(int32_t a, int32_t b)
{
    if (b < 0) return 0;
    if (b >= 32) return a < 0 ? -1 : 0;
    return a >> b;
}
static int32_t ti84py_pow(int32_t base, int32_t exponent)
{
    int32_t result = 1;
    if (exponent < 0) return 0;
    while (exponent) {
        if (exponent & 1) result *= base;
        base *= base;
        exponent >>= 1;
    }
    return result;
}
static int32_t ti84py_math_sign(int32_t v) { return v < 0 ? -1 : (v > 0 ? 1 : 0); }
static const int16_t ti84py_sin_q[91] = {0, 4, 9, 13, 18, 22, 27, 31, 36, 40, 44, 49, 53, 58, 62, 66, 71, 75, 79, 83, 88, 92, 96, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 139, 143, 147, 150, 154, 158, 161, 165, 168, 171, 175, 178, 181, 184, 187, 190, 193, 196, 199, 202, 204, 207, 210, 212, 215, 217, 219, 222, 224, 226, 228, 230, 232, 234, 236, 237, 239, 241, 242, 243, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 254, 255, 255, 255, 256, 256, 256, 256};
static int32_t ti84py_math_sin(int32_t deg)
{
    int32_t negative = 0, v;
    deg %= 360;
    if (deg < 0) deg += 360;
    if (deg >= 180) { negative = 1; deg -= 180; }
    if (deg > 90) deg = 180 - deg;
    v = ti84py_sin_q[deg];
    return negative ? -v : v;
}
static int32_t ti84py_math_cos(int32_t deg) { return ti84py_math_sin(deg + 90); }
static int32_t ti84py_random_between(int32_t low, int32_t high)
{
    if (high < low) return low;
    return low + ti84py_random_range(high - low + 1);
}
static int32_t ti84py_gfx_get_pixel(int32_t x, int32_t y)
{
    uint32_t offset;
    if ((uint32_t)x >= 320u || (uint32_t)y >= 240u) return 0;
    offset = (uint32_t)y * 320u + (uint32_t)x;
#if TI84PY_GRAPH_ENABLED
    if (ti84py_draw_buffer) return ti84py_index_rgb565(ti84py_buffer[offset]);
#endif
    return ti84py_vram[offset];
}
static int32_t ti84py_kb_is_down(int32_t code)
{
    volatile uint8_t *config = (volatile uint8_t*)0xF50000;
    int32_t group, bit;
    if (code < 1 || code > 56) return 0;
    *config = (uint8_t)((*config & ~3u) | 3u);   /* continuous scan */
    group = 7 - ((code - 1) >> 3);
    bit = (code - 1) & 7;
    return (((volatile uint16_t*)0xF50010)[group] >> bit) & 1;
}
static void ti84py_wait_key(void) { (void)ti84py_read_key(); }
static int32_t ti84py_int_to_str(char *out, int32_t value)
{
    char tmp[12];
    int32_t n = 0, len = 0;
    uint32_t u = value < 0 ? 0u - (uint32_t)value : (uint32_t)value;
    if (value < 0) out[len++] = '-';
    do { tmp[n++] = (char)('0' + u % 10u); u /= 10u; } while (u);
    while (n) out[len++] = tmp[--n];
    out[len] = 0;
    return len;
}
static void ti84py_gfx_text_int(int32_t value, int32_t x, int32_t y)
{
    char buffer[14];
    (void)ti84py_int_to_str(buffer, value);
    ti84py_gfx_text(buffer, x, y);
}
static char ti84py_line[64];
static int32_t ti84py_line_len = 0;
static uint8_t ti84py_printed = 0;
static void ti84py_print_flush(void)
{
    ti84py_line[ti84py_line_len] = 0;
    if (ti84py_text_row > 232) ti84py_gfx_clear();
    ti84py_gfx_text(ti84py_line, 0, ti84py_text_row);
    ti84py_text_row += 8;
    ti84py_line_len = 0;
    ti84py_printed = 1;
}
static void ti84py_put_ch(char c)
{
    if (c == '\n') { ti84py_print_flush(); return; }
    if (ti84py_line_len >= 52) ti84py_print_flush();
    ti84py_line[ti84py_line_len++] = c;
}
static void ti84py_print_str(const char *s) { while (*s) ti84py_put_ch(*s++); }
static void ti84py_print_int(int32_t value)
{
    char buffer[14];
    (void)ti84py_int_to_str(buffer, value);
    ti84py_print_str(buffer);
}
static void ti84py_print_bool(int32_t value) { ti84py_print_str(value ? "True" : "False"); }
static void ti84py_print_list(ti84py_list l)
{
    int32_t i;
    ti84py_put_ch('[');
    for (i = 0; i < l.len; ++i) {
        if (i) ti84py_print_str(", ");
        ti84py_print_int(l.data[i]);
    }
    ti84py_put_ch(']');
}
static void ti84py_finish(void)
{
    if (ti84py_line_len) ti84py_print_flush();
    if (ti84py_printed) ti84py_wait_key();
}
'''

MAIN_OPEN = "int main(void)\n{\n    ti84py_gfx_begin();"


def runtime_header(include_graph: bool = False) -> list[str]:
    """Return compiler-owned CE routines (everything before main) as C lines."""
    text = "#define TI84PY_GRAPH_ENABLED " + ("1" if include_graph else "0") + "\n#include <stdint.h>\n"
    if include_graph:
        colors = []
        for index in range(256):
            r, g, b = (index >> 5) & 7, (index >> 2) & 7, index & 3
            color = ((r * 31 // 7) << 11) | ((g * 63 // 7) << 5) | (b * 31 // 3)
            colors.append(f"0x{color:04X}")
        rows = [", ".join(colors[i:i + 8]) for i in range(0, 256, 8)]
        text += "#if TI84PY_GRAPH_ENABLED\nstatic const uint16_t ti84py_rgb565_palette[256] = {\n"
        text += ",\n".join(rows) + "\n};\n#endif\n"
    text += RUNTIME_C + RUNTIME_EXTRA_C
    return text.splitlines()
