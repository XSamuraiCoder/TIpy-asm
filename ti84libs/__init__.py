"""Built-in TI-84 libraries shipped separately from the compiler core."""

from __future__ import annotations

import ast

from . import font, fileioc, graphics, keyboard, math as mathlib, sprite, storage
from ti84asm.errors import CompileError


def emit_call(compiler, node: ast.Call) -> None:
    if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
        raise CompileError("unsupported function call")
    module = compiler.modules.get(node.func.value.id)
    if module == "ti84.graphics":
        graphics.emit_call(compiler, node)
    elif module == "ti84.storage":
        storage.emit_call(compiler, node)
    elif module == "ti84.keyboard":
        keyboard.emit_call(compiler, node)
    elif module == "ti84.font":
        font.emit_call(compiler, node)
    elif module == "ti84.sprite":
        sprite.emit_call(compiler, node)
    elif module == "ti84.fileioc":
        fileioc.emit_call(compiler, node)
    else:
        raise CompileError("import a library before calling it")


def emit_expression(compiler, node: ast.Call) -> None:
    if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
        raise CompileError("unsupported library expression")
    module = compiler.modules.get(node.func.value.id)
    if module == "ti84.storage" and node.func.attr == "read_byte":
        storage.emit_read_expression(compiler, node)
        return
    if module == "ti84.keyboard" and node.func.attr == "read":
        keyboard.emit_call(compiler, node)
        return
    if module == "ti84.math":
        mathlib.emit_expression(compiler, node)
        return
    if module == "ti84.font":
        font.emit_call(compiler, node)
        return
    if module == "ti84.sprite":
        sprite.emit_call(compiler, node)
        return
    if module == "ti84.fileioc":
        fileioc.emit_call(compiler, node)
        return
    raise CompileError("unsupported library expression")


def emit_attribute(compiler, node: ast.Attribute) -> None:
    if isinstance(node.value, ast.Name) and compiler.modules.get(node.value.id) == "ti84.graphics":
        graphics.emit_attribute(compiler, node)
        return
    if isinstance(node.value, ast.Name) and compiler.modules.get(node.value.id) == "ti84.keyboard":
        keyboard.emit_expression(compiler, node)
        return
    if isinstance(node.value, ast.Name) and compiler.modules.get(node.value.id) == "ti84.font":
        font.emit_call(compiler, node)
        return
    raise CompileError("unsupported library constant")
