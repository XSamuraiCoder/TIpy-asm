"""Lower TIpy's Python subset to C for CEdev-built CE Flash Apps.

Supported language (everything else is rejected with a line-numbered error):

* int / bool / str / list-of-int values, inferred from assignments, ``def``
  annotations (``x: str``, ``-> list``) and call sites
* ``def`` with positional/keyword/default arguments, recursion, ``global``
* ``if``/``elif``/``else``, ``while``, ``for`` over ``range()``, lists and strings,
  ``break``, ``continue``, ``pass``, ``return``, conditional expressions
* ``+ - * // % ** << >> & | ^ ~``, ``and``/``or``/``not``, chained comparisons,
  ``in``/``not in`` against literals and lists, tuple assignment / swap
* list literals, ``[x] * n``, indexing, ``len``, ``sum``, ``min``, ``max``, ``abs``
* ``print(..., sep=, end=)`` drawn on screen, plus the ``ti84.*`` libraries

Integers are 32-bit and wrap; ``//`` and ``%`` follow Python's floor semantics.
"""

from __future__ import annotations

import ast
import re

from .errors import CompileError
from .flash_ce import (
    LIBRARY_C, MAIN_OPEN, RGB565_COLORS, runtime_header,
)
from ti84libs.keyboard import key_code

INT, BOOL, STR, LIST, VOID = "int", "bool", "str", "list", "void"
KNOWN_MODULES = ("graphics", "keyboard", "storage", "file", "math", "random", "graph")
CTYPES = {INT: "int32_t", BOOL: "int32_t", STR: "const char *", LIST: "ti84py_list"}
ZERO = {INT: "0", BOOL: "0", STR: '""', LIST: "{0, 0}"}
ZERO_EXPR = {**ZERO, LIST: "(ti84py_list){0, 0}"}
INT_MIN, INT_MAX = -(2 ** 31), 2 ** 31 - 1


def _numeric(t: str) -> bool:
    return t in (INT, BOOL)


def _join(a: str, b: str) -> str | None:
    if a == b:
        return a
    if _numeric(a) and _numeric(b):
        return INT
    return None


class _Raw(ast.expr):
    """Pre-generated expression, used to desugar augmented assignment."""
    _fields = ()

    def __init__(self, code: str, ty: str):
        super().__init__()
        self.code, self.ty = code, ty


class _Func:
    def __init__(self, node: ast.FunctionDef):
        self.node = node
        self.name = node.name
        args = node.args
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs:
            raise CompileError(f"line {node.lineno}: only plain positional parameters are supported")
        self.params = [a.arg for a in args.args]
        defaults = [None] * (len(self.params) - len(args.defaults)) + list(args.defaults)
        self.defaults = dict(zip(self.params, defaults))
        self.annotations = {a.arg: a.annotation for a in args.args}
        self.globals: set[str] = set()
        self.locals: set[str] = set(self.params)
        for sub in ast.walk(node):
            if sub is node:
                continue
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                raise CompileError(f"line {getattr(sub, 'lineno', node.lineno)}: nested functions and classes are not supported")
            if isinstance(sub, ast.Global):
                self.globals.update(sub.names)
        for sub in ast.walk(node):
            for name in _assigned_names(sub):
                if name not in self.globals:
                    self.locals.add(name)


def _assigned_names(node: ast.AST) -> list[str]:
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        targets = [node.target]
    elif isinstance(node, ast.For):
        targets = [node.target]
    names: list[str] = []
    stack = targets
    while stack:
        t = stack.pop()
        if isinstance(t, ast.Name):
            names.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            stack.extend(t.elts)
    return names


class FlashAppCompiler:
    """Lower Python and TIpy library calls to a self-contained native app."""

    def __init__(self, app_name: str):
        self.app_name = re.sub(r"[^A-Za-z0-9_]", "_", app_name)[:8] or "PYAPP"
        self.modules: dict[str, str] = {}
        self.funcs: dict[str, _Func] = {}
        self.main_body: list[ast.stmt] = []
        self.global_names: set[str] = set()
        self.types: dict[tuple, str] = {}
        self.uses_graph = False
        self.uses_storage = False
        self.final = False
        self.cur: _Func | None = None
        self._reset()

    # ----------------------------------------------------------------- driver
    def _reset(self) -> None:
        self.out: list[str] = []
        self.ind = 1
        self.tmp = 0
        self.arrays: list[str] = []

    def compile(self, source: str) -> str:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise CompileError(f"line {exc.lineno}: {exc.msg}") from exc
        self._collect(tree)
        for _ in range(3):          # learn variable/return types; errors are not final yet
            self.final = False
            self._generate()
        self.final = True
        return self._generate()

    def _collect(self, tree: ast.Module) -> None:
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for item in stmt.names:
                    short = item.name.removeprefix("ti84.")
                    if not item.name.startswith("ti84.") or short not in KNOWN_MODULES or not item.asname:
                        raise CompileError(f"line {stmt.lineno}: import built-in libraries as 'import ti84.<name> as alias'")
                    self._register(item.asname, short)
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module != "ti84":
                    raise CompileError(f"line {stmt.lineno}: unsupported library import from {stmt.module}")
                for item in stmt.names:
                    if item.name not in KNOWN_MODULES:
                        raise CompileError(f"line {stmt.lineno}: unknown ti84 library: {item.name}")
                    self._register(item.asname or item.name, item.name)
            elif isinstance(stmt, ast.FunctionDef):
                if stmt.name in self.funcs:
                    raise CompileError(f"line {stmt.lineno}: function {stmt.name} defined twice")
                self.funcs[stmt.name] = _Func(stmt)
            else:
                self.main_body.append(stmt)
        for stmt in self.main_body:
            for sub in ast.walk(stmt):
                self.global_names.update(_assigned_names(sub))
        for fn in self.funcs.values():
            self.global_names.update(fn.globals)

    def _register(self, alias: str, short: str) -> None:
        self.modules[alias] = f"ti84.{short}"
        self.uses_graph |= short == "graph"
        self.uses_storage |= short == "storage"

    def _generate(self) -> str:
        self._reset()
        bodies: list[list[str]] = []
        for fn in self.funcs.values():
            self._init_param_types(fn)
            self.cur = fn
            self.out, self.ind = [], 1
            for stmt in fn.node.body:
                self.stmt(stmt)
            ret = self.types.get((fn.name, "<ret>"), INT)
            self.line(f"return {ZERO_EXPR[ret]};")
            body = self.out
            decls = []
            for name in sorted(fn.locals - set(fn.params)):
                ty = self.types.get((fn.name, name), INT)
                decls.append(f"    {CTYPES[ty]} l_{name} = {ZERO[ty]};")
            sig = self._signature(fn)
            bodies.append([sig, "{"] + decls + body + ["}", ""])
        self.cur = None
        self.out, self.ind = [], 1
        for stmt in self.main_body:
            self.stmt(stmt)
        main_lines = self.out
        main_lines.append("    ti84py_finish();")
        main_lines.append("    return 0;")

        protos = [self._signature(fn) + ";" for fn in self.funcs.values()]
        gdecls = []
        for name in sorted(self.global_names):
            ty = self.types.get(("", name), INT)
            gdecls.append(f"static {CTYPES[ty]} g_{name} = {ZERO[ty]};")
        lines = runtime_header(self.uses_graph) + self.arrays + gdecls + protos + [""]
        for body in bodies:
            lines.extend(body)
        lines.extend(MAIN_OPEN.splitlines())
        lines.extend(main_lines)
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _signature(self, fn: _Func) -> str:
        ret = self.types.get((fn.name, "<ret>"), INT)
        params = ", ".join(f"{CTYPES[self.types.get((fn.name, p), INT)]} l_{p}" for p in fn.params) or "void"
        return f"static {CTYPES[ret]} f_{fn.name}({params})"

    def _init_param_types(self, fn: _Func) -> None:
        for p in fn.params:
            ann = fn.annotations[p]
            if ann is not None:
                self.types[(fn.name, p)] = self._annotation(ann)
        ret = fn.node.returns
        if ret is not None and (fn.name, "<ret>") not in self.types:
            ty = self._annotation(ret)
            self.types[(fn.name, "<ret>")] = ty

    def _annotation(self, ann: ast.expr) -> str:
        if isinstance(ann, ast.Constant) and ann.value is None:
            return INT
        if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id == "list":
            return LIST
        if isinstance(ann, ast.Name) and ann.id in (INT, BOOL, STR, LIST):
            return ann.id
        raise CompileError(f"line {ann.lineno}: unsupported type annotation (use int, bool, str, or list)")

    # ---------------------------------------------------------------- helpers
    def line(self, text: str = "") -> None:
        self.out.append("    " * self.ind + text if text else "")

    def new_tmp(self) -> str:
        self.tmp += 1
        return f"t{self.tmp}"

    def fail(self, message: str) -> None:
        raise CompileError(message)

    def key(self, name: str, assign: bool = False) -> tuple:
        if self.cur and name in self.cur.locals and name not in self.cur.globals:
            return (self.cur.name, name)
        return ("", name)

    def cname(self, key: tuple) -> str:
        return ("l_" if key[0] else "g_") + key[1]

    def var(self, name: str) -> tuple[str, str]:
        if name in self.modules or name in self.funcs:
            self.fail(f"{name} cannot be used as a value")
        key = self.key(name)
        ty = self.types.get(key)
        if ty is None:
            if self.final:
                self.fail(f"name '{name}' is not defined")
            ty = INT
        return self.cname(key), ty

    def set_type(self, key: tuple, ty: str) -> None:
        old = self.types.get(key)
        if old is None:
            self.types[key] = ty
            return
        joined = _join(old, ty)
        if joined is None:
            if self.final:
                self.fail(f"variable '{key[1]}' changes type from {old} to {ty}")
            return
        if joined != old:
            if self.final:
                self.fail(f"variable '{key[1]}' changes type from {old} to {ty}")
            self.types[key] = joined

    # -------------------------------------------------------------- statements
    def stmt(self, node: ast.stmt) -> None:
        try:
            handler = getattr(self, "s_" + type(node).__name__, None)
            if handler is None:
                self.fail(f"unsupported statement {type(node).__name__}")
            handler(node)
        except CompileError as exc:
            if not self.final:
                return
            text = str(exc)
            if not text.startswith("line "):
                raise CompileError(f"line {node.lineno}: {text}") from None
            raise

    def block(self, body: list[ast.stmt]) -> None:
        self.ind += 1
        for child in body:
            self.stmt(child)
        self.ind -= 1

    def s_Pass(self, node): self.line(";")
    def s_Import(self, node): pass
    def s_ImportFrom(self, node): pass
    def s_Global(self, node): pass

    def s_Break(self, node): self.line("break;")
    def s_Continue(self, node): self.line("continue;")

    def s_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Constant):
            return                          # docstring or bare literal
        if isinstance(node.value, ast.Call):
            self.call(node.value, statement=True)
            return
        self.fail("expression statements must be calls")

    def s_Return(self, node: ast.Return) -> None:
        if not self.cur:
            self.fail("return outside a function")
        key = (self.cur.name, "<ret>")
        if node.value is None:
            self.line(f"return {ZERO_EXPR[self.types.get(key, INT)]};")
            return
        code, ty = self.expr(node.value)
        if ty == VOID:
            self.fail("cannot return a value-less call")
        self.set_type(key, ty)
        self.line(f"return {code};")

    def s_If(self, node: ast.If) -> None:
        test = node.test
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
                and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"):
            for child in node.body:
                self.stmt(child)
            return
        self.line(f"if ({self.cond(test)}) {{")
        self.block(node.body)
        if node.orelse:
            self.line("} else {")
            self.block(node.orelse)
        self.line("}")

    def s_While(self, node: ast.While) -> None:
        if node.orelse:
            self.fail("while/else is not supported")
        self.line(f"while ({self.cond(node.test)}) {{")
        self.block(node.body)
        self.line("}")

    def s_For(self, node: ast.For) -> None:
        if node.orelse:
            self.fail("for/else is not supported")
        if not isinstance(node.target, ast.Name):
            self.fail("for loops take a single loop variable")
        key = self.key(node.target.id)
        var = self.cname(key)
        it = node.iter
        n = self.new_tmp()
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range":
            if it.keywords or not 1 <= len(it.args) <= 3:
                self.fail("range() takes 1 to 3 positional arguments")
            self.set_type(key, INT)
            vals = [self.int_expr(a) for a in it.args]
            start, stop, step = ("0", vals[0], "1") if len(vals) == 1 else (vals[0], vals[1], vals[2] if len(vals) == 3 else "1")
            step_const = self.const_value(it.args[2]) if len(it.args) == 3 else 1
            if step_const == 0:
                self.fail("range() step must not be zero")
            self.line("{")
            self.ind += 1
            self.line(f"int32_t {n}i = {start}, {n}e = {stop}, {n}s = {step};")
            if step_const is None:
                cond = f"({n}s > 0 ? {n}i < {n}e : {n}i > {n}e)"
            else:
                cond = f"{n}i < {n}e" if step_const > 0 else f"{n}i > {n}e"
            self.line(f"for (; {cond}; {n}i += {n}s) {{")
            self.ind += 1
            self.line(f"{var} = {n}i;")
        else:
            code, ty = self.expr(it)
            if ty not in (LIST, STR):
                self.fail("for loops iterate over range(), a list, or a string")
            self.set_type(key, INT if ty == LIST else STR)
            self.line("{")
            self.ind += 1
            self.line(f"{CTYPES[ty]} {n}c = {code};")
            self.line(f"int32_t {n}i, {n}n = {n}c{'.len' if ty == LIST else ''};" if ty == LIST
                      else f"int32_t {n}i, {n}n = ti84py_strlen({n}c);")
            self.line(f"for ({n}i = 0; {n}i < {n}n; ++{n}i) {{")
            self.ind += 1
            self.line(f"{var} = {n}c.data[{n}i];" if ty == LIST else f"{var} = ti84py_str_char({n}c, {n}i);")
        for child in node.body:
            self.stmt(child)
        self.ind -= 1
        self.line("}")
        self.ind -= 1
        self.line("}")

    def s_Assign(self, node: ast.Assign) -> None:
        first = node.targets[0]
        if isinstance(first, (ast.Tuple, ast.List)):
            if len(node.targets) != 1 or not isinstance(node.value, (ast.Tuple, ast.List)) \
                    or len(first.elts) != len(node.value.elts):
                self.fail("tuple assignment needs a tuple of the same length on the right")
            temps = []
            for value in node.value.elts:
                code, ty = self.expr(value)
                t = self.new_tmp()
                self.line(f"{CTYPES[ty]} {t} = {code};")
                temps.append((t, ty))
            for target, (t, ty) in zip(first.elts, temps):
                self.assign_to(target, t, ty)
            return
        code, ty = self.expr(node.value)
        if len(node.targets) > 1:
            t = self.new_tmp()
            self.line(f"{CTYPES[ty]} {t} = {code};")
            code = t
        for target in node.targets:
            self.assign_to(target, code, ty)

    def s_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not isinstance(node.target, ast.Name):
            self.fail("annotated assignment needs a plain variable")
        key = self.key(node.target.id)
        declared = self._annotation(node.annotation)
        if key not in self.types:
            self.types[key] = declared
        if node.value is not None:
            code, ty = self.expr(node.value)
            self.assign_to(node.target, code, ty)

    def s_AugAssign(self, node: ast.AugAssign) -> None:
        target = node.target
        if isinstance(target, ast.Name):
            code, ty = self.expr(ast.copy_location(ast.BinOp(
                left=ast.Name(id=target.id, ctx=ast.Load()), op=node.op, right=node.value), node))
            self.assign_to(target, code, ty)
        elif isinstance(target, ast.Subscript):
            base, bt = self.expr(target.value)
            idx = self.int_expr(target.slice)
            if bt != LIST:
                self.fail("only list elements can be assigned by index")
            t = self.new_tmp()
            self.line(f"int32_t {t} = {idx};")
            current = _Raw(f"ti84py_list_get({base}, {t})", INT)
            code, ty = self.expr(ast.copy_location(ast.BinOp(left=current, op=node.op, right=node.value), node))
            self.line(f"ti84py_list_set({base}, {t}, {code});")
        else:
            self.fail("unsupported augmented assignment target")

    def assign_to(self, target: ast.expr, code: str, ty: str) -> None:
        if ty == VOID:
            self.fail("cannot assign a call that returns nothing")
        if isinstance(target, ast.Name):
            key = self.key(target.id, assign=True)
            self.set_type(key, ty)
            self.line(f"{self.cname(key)} = {code};")
        elif isinstance(target, ast.Subscript):
            base, bt = self.expr(target.value)
            if bt != LIST:
                self.fail("only list elements can be assigned by index")
            if not _numeric(ty):
                self.fail("lists hold integers only")
            self.line(f"ti84py_list_set({base}, {self.int_expr(target.slice)}, {code});")
        else:
            self.fail("unsupported assignment target")

    # ------------------------------------------------------------- expressions
    def expr(self, node: ast.expr) -> tuple[str, str]:
        handler = getattr(self, "x_" + type(node).__name__, None)
        if handler is None:
            self.fail(f"unsupported expression {type(node).__name__}")
        return handler(node)

    def int_expr(self, node: ast.expr) -> str:
        code, ty = self.expr(node)
        if not _numeric(ty):
            self.fail(f"expected an integer but found {ty}")
        return code

    def const_value(self, node: ast.expr) -> int | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self.const_value(node.operand)
            return -inner if inner is not None else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            a, b = self.const_value(node.left), self.const_value(node.right)
            if a is None or b is None:
                return None
            return a + b if isinstance(node.op, ast.Add) else a - b if isinstance(node.op, ast.Sub) else a * b
        return None

    def x__Raw(self, node: _Raw): return node.code, node.ty

    def x_Constant(self, node: ast.Constant) -> tuple[str, str]:
        v = node.value
        if isinstance(v, bool):
            return ("1" if v else "0"), BOOL
        if v is None:
            return "0", INT
        if isinstance(v, int):
            if not INT_MIN <= v <= INT_MAX:
                self.fail("integer constants must fit in 32 bits")
            return (str(v) if v != INT_MIN else "(-2147483647 - 1)"), INT
        if isinstance(v, str):
            return self.c_string(v), STR
        self.fail(f"unsupported constant {v!r} (floats and bytes are not supported)")

    @staticmethod
    def c_string(value: str) -> str:
        if not value.isascii():
            raise CompileError("strings must be ASCII")
        out = []
        for ch in value:
            if ch == "\n": out.append("\\n")
            elif ch == "\t": out.append("\\t")
            elif ch in '"\\': out.append("\\" + ch)
            elif ch == "?": out.append("\\?")       # avoid trigraphs
            elif 32 <= ord(ch) < 127: out.append(ch)
            else: out.append(f"\\{ord(ch):03o}")
        return '"' + "".join(out) + '"'

    def x_Name(self, node: ast.Name): return self.var(node.id)

    def x_Attribute(self, node: ast.Attribute) -> tuple[str, str]:
        if isinstance(node.value, ast.Name):
            module = self.modules.get(node.value.id)
            if module == "ti84.keyboard":
                code = key_code(node.attr)
                if code is None:
                    self.fail(f"unknown keyboard key name: {node.attr}")
                return str(code), INT
            if module == "ti84.graphics":
                color = RGB565_COLORS.get(node.attr.upper())
                if color is None:
                    self.fail(f"unknown graphics color: {node.attr}")
                return str(color), INT
        self.fail("unsupported attribute access")

    def x_UnaryOp(self, node: ast.UnaryOp) -> tuple[str, str]:
        if isinstance(node.op, ast.Not):
            return f"(!{self.cond(node.operand)})", BOOL
        code = self.int_expr(node.operand)
        if isinstance(node.op, ast.USub): return f"(-{code})", INT
        if isinstance(node.op, ast.UAdd): return code, INT
        if isinstance(node.op, ast.Invert): return f"(~{code})", INT
        self.fail("unsupported unary operator")

    def x_BinOp(self, node: ast.BinOp) -> tuple[str, str]:
        if isinstance(node.op, ast.Mult) and isinstance(node.left, ast.List):
            return self.list_fill(node.left, node.right)
        if isinstance(node.op, ast.Mult) and isinstance(node.right, ast.List):
            return self.list_fill(node.right, node.left)
        a, ta = self.expr(node.left)
        b, tb = self.expr(node.right)
        if isinstance(node.op, ast.Add) and ta == STR and tb == STR:
            self.fail("string concatenation is not supported; print the pieces separately")
        if not (_numeric(ta) and _numeric(tb)):
            self.fail(f"operator needs integers, found {ta} and {tb}")
        op = node.op
        simple = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^"}
        for kind, text in simple.items():
            if isinstance(op, kind):
                return f"({a} {text} {b})", INT
        helpers = {ast.FloorDiv: "ti84py_floordiv", ast.Mod: "ti84py_mod", ast.LShift: "ti84py_shl",
                   ast.RShift: "ti84py_shr", ast.Pow: "ti84py_pow"}
        for kind, name in helpers.items():
            if isinstance(op, kind):
                return f"{name}({a}, {b})", INT
        if isinstance(op, ast.Div):
            self.fail("true division '/' is not supported (no floats); use '//'")
        self.fail("unsupported binary operator")

    def x_BoolOp(self, node: ast.BoolOp) -> tuple[str, str]:
        parts = [self.expr(v) for v in node.values]
        ty = parts[0][1]
        for _, t in parts[1:]:
            joined = _join(ty, t)
            if joined is None:
                self.fail("and/or operands must have the same type")
            ty = joined
        code, _ = parts[-1]
        for value, vt in reversed(parts[:-1]):
            t = self.new_tmp()
            truth = self.truth(t, vt)
            pick = f"{truth} ? {t} : ({code})" if isinstance(node.op, ast.Or) else f"{truth} ? ({code}) : {t}"
            code = f"({{ {CTYPES[vt]} {t} = {value}; {pick}; }})"
        return code, ty

    def x_IfExp(self, node: ast.IfExp) -> tuple[str, str]:
        a, ta = self.expr(node.body)
        b, tb = self.expr(node.orelse)
        ty = _join(ta, tb)
        if ty is None:
            self.fail("both branches of a conditional expression must have the same type")
        return f"({self.cond(node.test)} ? {a} : {b})", ty

    def x_Compare(self, node: ast.Compare) -> tuple[str, str]:
        return self.cond_compare(node), BOOL

    def x_Subscript(self, node: ast.Subscript) -> tuple[str, str]:
        base, bt = self.expr(node.value)
        if isinstance(node.slice, ast.Slice):
            self.fail("slices are not supported")
        idx = self.int_expr(node.slice)
        if bt == LIST: return f"ti84py_list_get({base}, {idx})", INT
        if bt == STR: return f"ti84py_str_char({base}, {idx})", STR
        self.fail("only lists and strings can be indexed")

    def x_Tuple(self, node: ast.Tuple) -> tuple[str, str]:
        return self.x_List(node)

    def x_List(self, node: ast.List) -> tuple[str, str]:
        n = len(node.elts)
        items = [self.int_expr(e) for e in node.elts]
        buf = f"ti84py_arr_{len(self.arrays)}"
        self.arrays.append(f"static int32_t {buf}[{max(n, 1)}];")
        return f"ti84py_mklist({buf}, {n}, (const int32_t[]){{{', '.join(items) if items else '0'}}})", LIST

    def list_fill(self, lst: ast.List, count: ast.expr) -> tuple[str, str]:
        if len(lst.elts) != 1:
            self.fail("use [value] * count to build a list")
        n = self.const_value(count)
        if n is None or n < 0 or n > 8192:
            self.fail("list size must be a constant between 0 and 8192")
        value = self.int_expr(lst.elts[0])
        buf = f"ti84py_arr_{len(self.arrays)}"
        self.arrays.append(f"static int32_t {buf}[{max(n, 1)}];")
        return f"ti84py_mkfill({buf}, {n}, {value})", LIST

    # ------------------------------------------------------------- conditions
    def truth(self, code: str, ty: str) -> str:
        if ty == STR: return f"(*{code} != 0)"
        if ty == LIST: return f"({code}.len != 0)"
        return code

    def cond(self, node: ast.expr) -> str:
        if isinstance(node, ast.BoolOp):
            joiner = " || " if isinstance(node.op, ast.Or) else " && "
            return "(" + joiner.join(self.cond(v) for v in node.values) + ")"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"(!{self.cond(node.operand)})"
        if isinstance(node, ast.Compare):
            return self.cond_compare(node)
        code, ty = self.expr(node)
        if ty == VOID:
            self.fail("a call that returns nothing has no truth value")
        return self.truth(code, ty)

    def cond_compare(self, node: ast.Compare) -> str:
        operands = [node.left] + list(node.comparators)
        if len(node.ops) == 1:
            return self.compare_one(node.ops[0], operands[0], operands[1])
        # chained comparison: evaluate each middle operand once
        temps, pre = [], []
        for operand in operands:
            code, ty = self.expr(operand)
            t = self.new_tmp()
            pre.append(f"{CTYPES[ty]} {t} = {code};")
            temps.append(_Raw(t, ty))
        parts = [self.compare_one(op, temps[i], temps[i + 1]) for i, op in enumerate(node.ops)]
        return "({ " + " ".join(pre) + " " + " && ".join(parts) + "; })"

    def compare_one(self, op: ast.cmpop, left: ast.expr, right: ast.expr) -> str:
        if isinstance(op, (ast.In, ast.NotIn)):
            a = self.int_expr(left)
            if isinstance(right, (ast.Tuple, ast.List, ast.Set)):
                t = self.new_tmp()
                tests = " || ".join(f"{t} == {self.int_expr(e)}" for e in right.elts) or "0"
                code = f"({{ int32_t {t} = {a}; {tests}; }})"
            else:
                b, bt = self.expr(right)
                if bt != LIST:
                    self.fail("'in' needs a list or a literal tuple on the right")
                code = f"ti84py_list_contains({b}, {a})"
            return f"(!{code})" if isinstance(op, ast.NotIn) else code
        a, ta = self.expr(left)
        b, tb = self.expr(right)
        if ta == STR and tb == STR:
            if isinstance(op, ast.Eq): return f"ti84py_streq({a}, {b})"
            if isinstance(op, ast.NotEq): return f"(!ti84py_streq({a}, {b}))"
            self.fail("strings only support == and !=")
        if not (_numeric(ta) and _numeric(tb)):
            self.fail(f"cannot compare {ta} with {tb}")
        for kind, text in ((ast.Eq, "=="), (ast.NotEq, "!="), (ast.Lt, "<"), (ast.LtE, "<="),
                           (ast.Gt, ">"), (ast.GtE, ">=")):
            if isinstance(op, kind):
                return f"({a} {text} {b})"
        self.fail("unsupported comparison operator")

    # ------------------------------------------------------------------ calls
    def x_Call(self, node: ast.Call) -> tuple[str, str]:
        return self.call(node, statement=False)

    def call(self, node: ast.Call, statement: bool) -> tuple[str, str]:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in self.funcs:
                return self.user_call(self.funcs[func.id], node, statement)
            return self.builtin_call(func.id, node, statement)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = self.modules.get(func.value.id)
            if module:
                return self.library_call(module, func.attr, node, statement)
            self.fail("methods are not supported; lists are fixed size and strings are immutable")
        self.fail("unsupported call target")

    def finish_call(self, code: str, ty: str, statement: bool) -> tuple[str, str]:
        if statement:
            self.line(f"(void){code};" if ty != VOID else f"{code};")
            return "", VOID
        if ty == VOID:
            self.fail("this call returns no value")
        return code, ty

    def bind(self, node: ast.Call, names: list[str], defaults: dict, what: str) -> dict[str, ast.expr]:
        bound: dict[str, ast.expr] = {}
        if len(node.args) > len(names):
            self.fail(f"{what} takes at most {len(names)} arguments")
        for name, arg in zip(names, node.args):
            if isinstance(arg, ast.Starred):
                self.fail("* arguments are not supported")
            bound[name] = arg
        for kw in node.keywords:
            if kw.arg is None or kw.arg not in names:
                self.fail(f"{what} has no parameter named {kw.arg}")
            if kw.arg in bound:
                self.fail(f"{what} got multiple values for {kw.arg}")
            bound[kw.arg] = kw.value
        for name in names:
            if name not in bound:
                if defaults.get(name) is None:
                    self.fail(f"{what} is missing argument {name}")
        return bound

    def user_call(self, fn: _Func, node: ast.Call, statement: bool) -> tuple[str, str]:
        bound = self.bind(node, fn.params, fn.defaults, f"{fn.name}()")
        args = []
        for p in fn.params:
            source = bound.get(p, fn.defaults.get(p))
            code, ty = self.expr(source)
            key = (fn.name, p)
            if fn.annotations[p] is None and not self.final:
                self.set_type(key, ty)
            want = self.types.get(key, INT)
            if want != ty and _join(want, ty) != want:
                self.fail(f"{fn.name}() parameter {p} expects {want}, got {ty}")
            args.append(code)
        ret = self.types.get((fn.name, "<ret>"), INT)
        return self.finish_call(f"f_{fn.name}({', '.join(args)})", ret, statement)

    def library_call(self, module: str, attr: str, node: ast.Call, statement: bool) -> tuple[str, str]:
        entry = LIBRARY_C.get(module, {}).get(attr)
        if entry is None:
            self.fail(f"{module.removeprefix('ti84.')} has no function {attr}()")
        template, params, ret = entry
        names = [p[0] for p in params]
        defaults = {p[0]: p[2] for p in params}
        bound = self.bind(node, names, defaults, f"{module.removeprefix('ti84.')}.{attr}()")
        args = []
        for name, kind, default in params:
            source = bound.get(name)
            if source is None:
                args.append(str(default))
            elif kind == "i":
                args.append(self.int_expr(source))
            elif kind == "s":
                code, ty = self.expr(source)
                if ty != STR:
                    self.fail(f"{attr}() parameter {name} must be a string")
                args.append(code)
            else:   # AppVar name literal
                if not isinstance(source, ast.Constant) or not isinstance(source.value, str):
                    self.fail("AppVar name must be a string literal")
                text = source.value.upper()
                if not re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", text):
                    self.fail("AppVar names must be 1-8 ASCII letters/digits")
                args.append(self.c_string(text))
        code = template[1:].format(*args) if template.startswith("=") else f"{template}({', '.join(args)})"
        ty = {"v": VOID, "i": INT, "b": BOOL}[ret]
        return self.finish_call(code, ty, statement)

    def builtin_call(self, name: str, node: ast.Call, statement: bool) -> tuple[str, str]:
        if name == "print":
            if not statement:
                self.fail("print() returns no value")
            return self.print_call(node)
        if node.keywords:
            self.fail(f"{name}() takes positional arguments only")
        args = [self.expr(a) for a in node.args]
        n = len(args)
        if name == "len" and n == 1:
            code, ty = args[0]
            if ty == LIST: return self.finish_call(f"({code}).len", INT, statement)
            if ty == STR: return self.finish_call(f"ti84py_strlen({code})", INT, statement)
        elif name == "abs" and n == 1 and _numeric(args[0][1]):
            return self.finish_call(f"ti84py_math_abs({args[0][0]})", INT, statement)
        elif name in ("min", "max") and n >= 1:
            if n == 1 and args[0][1] == LIST:
                return self.finish_call(f"ti84py_list_{name}({args[0][0]})", INT, statement)
            if n >= 2 and all(_numeric(t) for _, t in args):
                code = args[0][0]
                for other, _ in args[1:]:
                    code = f"ti84py_math_{name}({code}, {other})"
                return self.finish_call(code, INT, statement)
        elif name == "sum" and n == 1 and args[0][1] == LIST:
            return self.finish_call(f"ti84py_list_sum({args[0][0]})", INT, statement)
        elif name == "int" and n == 1 and _numeric(args[0][1]):
            return self.finish_call(args[0][0], INT, statement)
        elif name == "bool" and n == 1:
            return self.finish_call(self.truth(*args[0]), BOOL, statement)
        elif name == "ord" and n == 1 and args[0][1] == STR:
            return self.finish_call(f"ti84py_str_at({args[0][0]}, 0)", INT, statement)
        self.fail(f"unsupported call to {name}() with these arguments")

    def print_call(self, node: ast.Call) -> tuple[str, str]:
        sep, end = " ", "\n"
        for kw in node.keywords:
            if kw.arg in ("sep", "end") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                if kw.arg == "sep": sep = kw.value.value
                else: end = kw.value.value
            else:
                self.fail("print() accepts sep= and end= string literals only")
        for i, arg in enumerate(node.args):
            if i and sep:
                self.line(f"ti84py_print_str({self.c_string(sep)});")
            code, ty = self.expr(arg)
            if ty == STR: self.line(f"ti84py_print_str({code});")
            elif ty == BOOL: self.line(f"ti84py_print_bool({code});")
            elif ty == LIST: self.line(f"ti84py_print_list({code});")
            elif ty == INT: self.line(f"ti84py_print_int({code});")
            else: self.fail("cannot print a call that returns nothing")
        if end:
            self.line(f"ti84py_print_str({self.c_string(end)});")
        return "", VOID
