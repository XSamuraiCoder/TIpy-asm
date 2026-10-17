"""Keyboard input and key constants for both calculator architectures."""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError


# GetCSC scan codes (CEdev ti/getcsc.h sk_* values). Digit keys are KEY_0..KEY_9.
KEYS = {
    "DOWN": 0x01, "LEFT": 0x02, "RIGHT": 0x03, "UP": 0x04,
    "ENTER": 0x09, "ADD": 0x0A, "SUB": 0x0B, "MUL": 0x0C, "DIV": 0x0D, "POWER": 0x0E,
    "CLEAR": 0x0F, "CHS": 0x11, "3": 0x12, "6": 0x13, "9": 0x14, "RPAREN": 0x15,
    "TAN": 0x16, "VARS": 0x17, "DECPNT": 0x19, "2": 0x1A, "5": 0x1B, "8": 0x1C,
    "LPAREN": 0x1D, "COS": 0x1E, "PRGM": 0x1F, "STAT": 0x20, "0": 0x21, "1": 0x22,
    "4": 0x23, "7": 0x24, "COMMA": 0x25, "SIN": 0x26, "APPS": 0x27, "GRAPHVAR": 0x28,
    "STORE": 0x2A, "LN": 0x2B, "LOG": 0x2C, "SQUARE": 0x2D, "RECIP": 0x2E, "MATH": 0x2F,
    "ALPHA": 0x30, "GRAPH": 0x31, "TRACE": 0x32, "ZOOM": 0x33, "WINDOW": 0x34,
    "YEQU": 0x35, "SECOND": 0x36, "MODE": 0x37, "DEL": 0x38,
}


def key_code(name: str) -> int | None:
    """Look up ``keyboard.<name>``; accepts DOWN, down, KEY_DOWN, KEY_0."""
    key = name.upper()
    if key.startswith("KEY_"):
        key = key[4:]
    return KEYS.get(key)


def emit_call(compiler, node: ast.Call) -> None:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "read" or node.args or node.keywords:
        raise CompileError("keyboard supports read() with no arguments")

    released = compiler.label("key_release")
    wait = compiler.label("key_wait")
    if compiler.target == "classic":
        compiler.emit(released + ":")
        compiler.emit("    bcall(_GetCSC)")
        compiler.emit("    or a")
        compiler.emit(f"    jr nz,{released}")
        compiler.emit(wait + ":")
        compiler.emit("    bcall(_GetCSC)")
        compiler.emit("    or a")
        compiler.emit(f"    jr z,{wait}")
        compiler.emit("    ld l,a")
        compiler.emit("    ld h,0")
    else:
        compiler.emit(released + ":")
        compiler.emit("    call ti.GetCSC")
        compiler.emit("    or a,a")
        compiler.emit(f"    jr nz,{released}")
        compiler.emit(wait + ":")
        compiler.emit("    call ti.GetCSC")
        compiler.emit("    or a,a")
        compiler.emit(f"    jr z,{wait}")
        compiler.emit("    ld l,a")
        compiler.emit("    ld h,0")


def emit_expression(compiler, node: ast.Attribute) -> None:
    if not isinstance(node.value, ast.Name):
        raise CompileError("keyboard constants use keyboard.KEY_NAME")
    code = key_code(node.attr)
    if code is None:
        raise CompileError(f"unknown keyboard key: {node.attr}")
    compiler.emit(f"    ld hl,{code}")