"""Pseudo-random integers for assembly targets, implemented in the runtime prelude."""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError

ARITY = {"seed": 1, "randrange": 1, "randint": 2}


def emit_call(compiler, node: ast.Call) -> None:
    method = node.func.attr
    if node.keywords or len(node.args) != ARITY[method]:
        raise CompileError(f"random.{method}() takes {ARITY[method]} positional argument(s)")
    compiler.call_function(f"_tipy_{method}", list(node.args))
