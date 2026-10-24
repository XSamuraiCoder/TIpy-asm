"""CE graphics lifecycle calls currently implemented by TIpy's runtime.

Drawing targets the visible VRAM directly. This module intentionally exposes
only begin/end until TIpy has a safe offscreen framebuffer implementation.
"""

GRAPH_API = {
    "begin": (0, 0),
    "end": (0, 0),
}
