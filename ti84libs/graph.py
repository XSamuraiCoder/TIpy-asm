"""GraphX-inspired frame and draw-target controls for TI-84 CE Flash Apps.

Drawing primitives live in :mod:`ti84.graphics`; this module controls whether
they target the LCD or TIpy's offscreen indexed-color frame and when that frame
is copied to the display.
"""

GRAPH_API = {
    "begin": (0, 0),
    "end": (0, 0),
    "set_draw_buffer": (0, 0),
    "set_draw_screen": (0, 0),
    "swap_draw": (0, 0),
    "blit_buffer": (0, 0),
    "blit_screen": (0, 0),
}
