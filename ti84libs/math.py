"""Integer math helpers for assembly targets."""

import ast

from ti84asm.errors import CompileError


ARITY = {"abs": 1, "min": 2, "max": 2, "clamp": 3, "sign": 1, "sqrt": 1, "pow": 2, "sin": 1, "cos": 1}


def emit_expression(compiler, node: ast.Call) -> None:
    """Emit target-width integer math for standalone assembly builds."""
    method = node.func.attr
    if node.keywords:
        raise CompileError("assembly math calls must use positional arguments")
    if len(node.args) != ARITY[method]:
        raise CompileError(f"math.{method}() takes {ARITY[method]} argument(s), got {len(node.args)}")

    if method in ("sqrt", "pow", "sin", "cos", "min", "max"):
        compiler.call_function(f"_tipy_{method}", list(node.args))
    elif method == "abs":
        compiler.expression(node.args[0])
        compiler.use_helper("_rt_abs")
        compiler.emit("    call _rt_abs")
    elif method == "clamp":
        value, low, high = node.args
        compiler.call_function("_tipy_max", [ast.Call(func=ast.Name(id="_tipy_min", ctx=ast.Load()),
                                                      args=[value, high], keywords=[]), low])
    elif method == "sign":
        compiler.expression(node.args[0])
        negative, zero, done = (compiler.label(stem) for stem in
                                ("math_sign_negative", "math_sign_zero", "math_sign_done"))
        compiler.emit("    ld de,0")
        compiler.emit("    or a")
        compiler.emit("    sbc hl,de")
        compiler.emit(f"    jp m,{negative}")
        compiler.emit(f"    jp z,{zero}")
        compiler.emit("    ld hl,1")
        compiler.emit(f"    jp {done}")
        compiler.emit(negative + ":")
        compiler.emit(f"    ld hl,{compiler.integer_literal(-1)}")
        compiler.emit(f"    jp {done}")
        compiler.emit(zero + ":")
        compiler.emit("    ld hl,0")
        compiler.emit(done + ":")
