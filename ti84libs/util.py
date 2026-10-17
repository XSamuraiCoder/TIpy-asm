"""Shared helpers for bundled calculator libraries."""

import ast

from ti84asm.errors import CompileError


def literal_integer(node: ast.expr, purpose: str, allow_unsigned: bool = False) -> int:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, int) or isinstance(node.value, bool):
        raise CompileError(f"{purpose} must be integer literals for this library")
    minimum, maximum = (0, 65535) if allow_unsigned else (0, 32767)
    if not minimum <= node.value <= maximum:
        raise CompileError(f"{purpose} must be in the range {minimum}..{maximum}")
    return node.value
