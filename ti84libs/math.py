"""Integer math helpers for assembly and CE Flash App targets."""

import ast

from ti84asm.errors import CompileError

MATH_API = {
    "abs": (1, 1),
    "min": (2, 2),
    "max": (2, 2),
    "clamp": (3, 3),
    "sqrt": (1, 1),
}


def emit_expression(compiler, node: ast.Call) -> None:
    """Emit the architecture-neutral integer helpers supported by asm output."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "abs" or len(node.args) != 1 or node.keywords:
        raise CompileError("assembly targets currently support math.abs(value)")
    compiler.expression(node.args[0])
    done = compiler.label("math_abs_done")
    compiler.emit("    bit 7,h")
    compiler.emit(f"    jr z,{done}")
    compiler.emit("    xor a")
    compiler.emit("    sub l")
    compiler.emit("    ld l,a")
    compiler.emit("    sbc a,a")
    compiler.emit("    sub h")
    compiler.emit("    ld h,a")
    compiler.emit(done + ":")
