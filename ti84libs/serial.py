"""Serial bytes: USB serial on the TI-84 Plus CE, and the link port on classic calculators.

On the CE, TIpy's own USB driver makes the calculator a USB serial device
(CDC-ACM, 16C0:05E1, as CEdev's srldrvce) when it is plugged into a computer.
It needs no LibLoad or CE C libraries. The calculator cannot yet be the USB
host for an Arduino or another calculator.

On classic calculators, it sends and receives bytes over the 2.5 mm link port
with the OS's own routines, so two calculators running TIpy programs, or any
program using the same OS calls, can talk.
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError
from ti84asm.runtime import LabelRef

_ARITY = {"begin": (0, 1), "end": (0,), "connected": (0,), "read_byte": (0,), "write_byte": (1,),
          "write": (1,), "write_int": (1,)}


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    if node.keywords:
        raise CompileError(f"serial.{method}() uses positional arguments")
    if len(node.args) not in _ARITY[method]:
        raise CompileError(f"serial.{method}() takes {' or '.join(map(str, _ARITY[method]))} argument(s)")
    args = list(node.args)
    ce = compiler.target == "ce"
    if method == "begin":
        if ce:
            if args:
                compiler.expression(args[0])    # a computer sets the baud rate of a USB serial port
            compiler.call_raw("_rt_usb_init", [])
        else:
            if args:
                compiler.expression(args[0])        # evaluated for its effects, as on CE
            compiler.emit("    ld hl,0")
    elif method == "end":
        if ce:
            compiler.call_raw("_rt_usb_end", [])
    elif method == "connected":
        if ce:
            compiler.call_raw("_rt_srl_connected", [])
        else:
            compiler.emit("    ld hl,1")
    elif method == "read_byte":
        compiler.call_raw("_rt_srl_read_byte" if ce else "_rt_link_read_byte", [])
    elif method == "write_byte":
        compiler.call_raw("_rt_srl_write_byte" if ce else "_rt_link_write_byte", args)
    elif method == "write":
        text = args[0]
        if not isinstance(text, ast.Constant) or not isinstance(text.value, str):
            raise CompileError("serial.write() takes a string literal; use write_int() for numbers")
        try:
            encoded = text.value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise CompileError("serial.write() sends ASCII text only") from exc
        label = compiler.label("serial_text")
        compiler.data_bytes(label, list(encoded) or [0])
        compiler.call_raw("_rt_usb_send" if ce else "_rt_link_write", [LabelRef(label), ast.Constant(len(encoded))])
    elif method == "write_int":
        # The decimal text ends at _rt_it_buf + 9; its length is the distance from the start.
        compiler.expression(args[0])
        compiler.use_helper("_rt_itoa")
        compiler.emit("    call _rt_itoa")
        write = "_rt_usb_send" if ce else "_rt_link_write"
        compiler.use_helper(write)
        compiler.emit("    ld (_rt_a0),hl")
        compiler.emit("    ex de,hl")
        compiler.emit("    ld hl,_rt_it_buf+9")
        compiler.emit("    or a,a" if ce else "    or a")
        compiler.emit("    sbc hl,de")
        compiler.emit("    ld (_rt_a1),hl")
        compiler.emit(f"    call {write}")
