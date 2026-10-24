"""Integer math helpers for assembly and CE Flash App targets."""

import ast

from ti84asm.errors import CompileError


# Helpers emitted by the standalone assembly backend. The CE Flash App backend
# has a larger C runtime API, recorded separately in ti84asm.flash_ce.
MATH_API = {
    "abs": (1, 1),
    "min": (2, 2),
    "max": (2, 2),
    "clamp": (3, 3),
    "sign": (1, 1),
}


def emit_expression(compiler, node: ast.Call) -> None:
    """Emit target-width integer math for standalone assembly builds."""
    if not isinstance(node.func, ast.Attribute) or node.keywords:
        raise CompileError("assembly math calls must use positional arguments")
    method = node.func.attr
    arity = MATH_API.get(method)
    if arity is None or len(node.args) not in arity:
        supported = ", ".join(f"math.{name}()" for name in MATH_API)
        raise CompileError(f"assembly math supports {supported}")

    if method == "abs":
        compiler.expression(node.args[0])
        done = compiler.label("math_abs_done")
        if compiler.target == "ce":
            # CE integers are signed 24-bit values, so test the processor's
            # arithmetic sign flag rather than bit 7 of the 16-bit H register.
            compiler.emit("    ld de,0")
            compiler.emit("    or a")
            compiler.emit("    sbc hl,de")
            compiler.emit(f"    jp p,{done}")
            compiler.emit("    ld de,0")
            compiler.emit("    ex de,hl")
            compiler.emit("    or a")
            compiler.emit("    sbc hl,de")
        else:
            compiler.emit("    bit 7,h")
            compiler.emit(f"    jr z,{done}")
            compiler.emit("    xor a")
            compiler.emit("    sub l")
            compiler.emit("    ld l,a")
            compiler.emit("    sbc a,a")
            compiler.emit("    sub h")
            compiler.emit("    ld h,a")
        compiler.emit(done + ":")
    elif method in ("min", "max"):
        left, right = (_save_value(compiler, arg) for arg in node.args)
        op = ast.Lt() if method == "min" else ast.Gt()
        choose_right, done = compiler.label("math_choose_right"), compiler.label("math_choose_done")
        _emit_compare_branch(compiler, left, op, right, choose_right)
        compiler.emit(f"    ld hl,({compiler.variable(left)})")
        compiler.emit(f"    jp {done}")
        compiler.emit(choose_right + ":")
        compiler.emit(f"    ld hl,({compiler.variable(right)})")
        compiler.emit(done + ":")
    elif method == "clamp":
        value, low, high = (_save_value(compiler, arg) for arg in node.args)
        use_low = compiler.label("math_clamp_low")
        check_high = compiler.label("math_clamp_high")
        use_high = compiler.label("math_clamp_use_high")
        done = compiler.label("math_clamp_done")
        _emit_compare_branch(compiler, value, ast.Lt(), low, check_high)
        compiler.emit(use_low + ":")
        compiler.emit(f"    ld hl,({compiler.variable(low)})")
        compiler.emit(f"    jp {done}")
        compiler.emit(check_high + ":")
        _emit_compare_branch(compiler, value, ast.Gt(), high, use_high)
        compiler.emit(f"    ld hl,({compiler.variable(value)})")
        compiler.emit(f"    jp {done}")
        compiler.emit(use_high + ":")
        compiler.emit(f"    ld hl,({compiler.variable(high)})")
        compiler.emit(done + ":")
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


def _save_value(compiler, expression: ast.expr) -> str:
    name = compiler.label("math_arg")
    label = compiler.variable(name)
    compiler.expression(expression)
    compiler.emit(f"    ld ({label}),hl")
    compiler.mark_assigned(name)
    return name


def _emit_compare_branch(compiler, left: str, op: ast.cmpop, right: str, false_label: str) -> None:
    compiler.condition_false(
        ast.Compare(left=ast.Name(id=left, ctx=ast.Load()), ops=[op],
                    comparators=[ast.Name(id=right, ctx=ast.Load())]),
        false_label,
    )
