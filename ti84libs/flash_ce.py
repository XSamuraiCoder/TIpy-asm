"""Compatibility exports for TIpy's CE Flash App runtime.

The implementation lives in :mod:`ti84asm.flash_ce`, beside the compiler
backend that emits it. Keeping this module as a shim avoids maintaining two
different copies of the native runtime and library call table.
"""

from ti84asm.flash_ce import (
    LIBRARY_API,
    LIBRARY_C,
    MAIN_OPEN,
    RGB565_COLORS,
    RUNTIME_C,
    RUNTIME_EXTRA_C,
    runtime_header,
    supported_call,
)

__all__ = [
    "LIBRARY_API",
    "LIBRARY_C",
    "MAIN_OPEN",
    "RGB565_COLORS",
    "RUNTIME_C",
    "RUNTIME_EXTRA_C",
    "runtime_header",
    "supported_call",
]
