"""USB on the TI-84 Plus CE, with TIpy's own driver: no LibLoad or CE C libraries.

The calculator is a USB device: plugged into a computer, it is a USB serial
port (see ti84.serial). This library reports the USB state: whether a computer
has set the calculator up, the role, and the latest event.

USB host mode, where the calculator talks to a keyboard, a drive, or another
device on an OTG cable, is not supported yet: find() finds nothing, and the
device and transfer methods report failure.
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError
from ti84asm.usbrt import EVENTS, USB_ERROR_NOT_SUPPORTED

CONSTANTS = {
    "HOST": 0, "DEVICE": 1 << 4, "PLUG_A": 0, "PLUG_B": 1 << 5,
    "FULL_SPEED": 0, "LOW_SPEED": 1 << 4,
    **EVENTS,
}

_ARITY = {"begin": 0, "end": 0, "poll": 0, "role": 0, "last_event": 0, "find": (0, 1), "connected": 0,
          "vendor_id": 1, "product_id": 1, "address": 1, "speed": 1, "configure": 1, "transfer": 5,
          "control": 6, "buffer_get": 1, "buffer_set": 2}
# Host mode is not supported yet: these evaluate their arguments, then give this.
_NO_HOST = {"find": 0, "vendor_id": -1, "product_id": -1, "address": -1, "speed": -1,
            "configure": USB_ERROR_NOT_SUPPORTED, "transfer": -1, "control": -1}


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
        compiler.call_raw("_rt_usb_init", [])
    elif method == "end":
        compiler.call_raw("_rt_usb_end", [])
    elif method == "poll":
        compiler.call_raw("_rt_usb_poll", [])
    elif method == "role":
        compiler.call_raw("_rt_usb_role", [])
    elif method == "last_event":
        compiler.use_helper("_rt_usb_init")
        compiler.emit("    ld hl,(_rt_usb_event)")
    elif method == "connected":
        compiler.call_raw("_rt_srl_connected", [])
    elif method == "buffer_get":
        compiler.call_raw("_rt_usb_peek", args)
    elif method == "buffer_set":
        compiler.call_raw("_rt_usb_poke", args)
    else:
        if method == "transfer" and not (isinstance(args[2], ast.Constant) and isinstance(args[2].value, str)):
            raise CompileError("usb.transfer() takes the buffer AppVar's name as a string literal")
        for argument in args:
            if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
                compiler.expression(argument)
        compiler.emit(f"    ld hl,{compiler.integer_literal(_NO_HOST[method])}")
