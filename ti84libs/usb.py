"""USB on the TI-84 Plus CE, through CEdev's usbdrvce library (loaded by LibLoad).

The calculator can be the USB host, for a keyboard, a flash drive, an Arduino, or
another calculator on an OTG cable, or a device, for a computer. ti84.serial
covers serial ports; this library covers everything else: events, finding
devices, their IDs, and control and bulk transfers.
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError
from ti84asm.runtime import LabelRef
from ti84asm.usbrt import EVENTS

from .storage import appvar_label

CONSTANTS = {
    "HOST": 0, "DEVICE": 1 << 4, "PLUG_A": 0, "PLUG_B": 1 << 5,
    "FULL_SPEED": 0, "LOW_SPEED": 1 << 4,
    **EVENTS,
}

_RAW = {"begin": "_rt_usb_init", "end": "_rt_usb_end", "poll": "_rt_usb_poll", "role": "_rt_usb_role",
        "find": "_rt_usb_find", "address": "_rt_usb_address", "speed": "_rt_usb_speed",
        "configure": "_rt_usb_configure", "buffer_get": "_rt_usb_peek", "buffer_set": "_rt_usb_poke"}
_ARITY = {"begin": 0, "end": 0, "poll": 0, "role": 0, "last_event": 0, "find": (0, 1), "connected": 0,
          "vendor_id": 1, "product_id": 1, "address": 1, "speed": 1, "configure": 1, "transfer": 5,
          "control": 6, "buffer_get": 1, "buffer_set": 2}
# Offsets in the 18-byte device descriptor.
_DESCRIPTOR_WORDS = {"vendor_id": 8, "product_id": 10}


def constant(name: str) -> int | None:
    return CONSTANTS.get(name)


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    if node.keywords:
        raise CompileError(f"usb.{method}() uses positional arguments")
    arity = _ARITY[method]
    counts = arity if isinstance(arity, tuple) else (arity,)
    if len(node.args) not in counts:
        raise CompileError(f"usb.{method}() takes {' or '.join(map(str, counts))} argument(s)")
    args = list(node.args)
    if method == "begin":
        # No device descriptors: the calculator uses its own when a computer is the host.
        compiler.call_raw("_rt_usb_init", [ast.Constant(0)])
    elif method == "find":
        compiler.call_raw("_rt_usb_find", args or [ast.Constant(0)])
    elif method == "last_event":
        compiler.use_helper("_rt_usb_init")
        compiler.emit("    ld hl,(_rt_usb_event)")
    elif method == "connected":
        compiler.call_raw("_rt_usb_poll", [])
        compiler.call_raw("_rt_usb_find", [ast.Constant(0)])
        done = compiler.label("usb_connected")
        compiler.emit("    ld de,0")
        compiler.emit("    or a,a")
        compiler.emit("    sbc hl,de")
        compiler.emit(f"    jr z,{done}")
        compiler.emit("    ld hl,1")
        compiler.emit(f"{done}:")
    elif method in _DESCRIPTOR_WORDS:
        compiler.call_raw("_rt_usb_descriptor_word", [args[0], ast.Constant(_DESCRIPTOR_WORDS[method])])
    elif method == "transfer":
        name = args[2]
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            raise CompileError("usb.transfer() takes the buffer AppVar's name as a string literal")
        label = LabelRef(appvar_label(compiler, name.value.upper()))
        compiler.call_raw("_rt_usb_transfer", [args[0], label, args[3], args[4], args[1]])
    elif method == "control":
        compiler.call_raw("_rt_usb_set_setup", args[1:])
        compiler.call_raw("_rt_usb_control", [args[0]])
    else:
        compiler.call_raw(_RAW[method], args)
