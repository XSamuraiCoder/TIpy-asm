#!/usr/bin/env python3
"""Compile a small, typed Python subset to TI-83+/TI-84 Z80 or CE eZ80 assembly."""

from __future__ import annotations

import ast
import difflib
import re
import sys
from pathlib import Path

from .errors import CompileError
from .runtime import MAX_RAW_ARGS, RAW, LabelRef, Target, prelude_tree, render

# ti84libs is a sibling package. Make that sibling visible when Python starts
# the installed console-script launcher, whose initial sys.path may omit cwd.
_PACKAGE_ROOT = str(Path(__file__).resolve().parent.parent)
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

from ti84libs import assembly_libraries, constant_library, emit_attribute, emit_call, library_error

_LINE_PREFIX = re.compile(r"line \d+:")
_ASM_EXPORT = re.compile(r"^[ \t]*;[ \t]*tipy:[ \t]*def[ \t]+(\w+)[ \t]*\(([^)]*)\)", re.MULTILINE)
_ASM_REGISTERS = ("hl", "de", "bc")
_RESERVED_LABELS = ("start", "program_exit")
_BUILTIN_FUNCTIONS = ("print", "exit", "abs", "min", "max", "range")


def _describe(node: ast.AST) -> str:
    names = {"Dict": "dictionaries", "Set": "sets", "ListComp": "list comprehensions", "JoinedStr": "f-strings",
             "Lambda": "lambda functions", "Await": "await", "Yield": "generators", "Div": "true division (use //)",
             "Pow": "the ** operator (use math.pow)", "MatMult": "the @ operator"}
    kind = type(node).__name__
    if isinstance(node, ast.BinOp):
        kind = type(node.op).__name__
    if isinstance(node, ast.Constant):
        return f"{type(node.value).__name__} values such as {node.value!r} (assembly integers only)"
    return names.get(kind, f"{kind} expressions")


def _store_names(body: list[ast.stmt]) -> set[str]:
    """Names a block of statements assigns, not looking inside nested functions."""
    names: set[str] = set()
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.FunctionDef):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        stack.extend(ast.iter_child_nodes(node))
    return names


def _called_names(node: ast.AST) -> set[str]:
    return {sub.func.id for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)}


class Compiler:
    def __init__(self, program: str, target: str = "classic", source_dir: Path | None = None):
        if target not in {"classic", "ce"}:
            raise CompileError("compiler target must be 'classic' or 'ce'")
        # TI program names are limited to eight alphanumeric characters.
        # Strip filename punctuation so ordinary stems such as "my_demo"
        # produce a valid calculator name by default.
        self.program = re.sub(r"[^A-Za-z0-9]", "", program.upper())[:8] or "PYPROG"
        self.target = target
        self.spec = Target(target)
        # Where `from name import routine` looks for name.asm or name.s.
        self.source_dir = source_dir
        self._reset()

    def _reset(self) -> None:
        self.lines: list[str] = []
        self.data: list[str] = []
        self.variables: dict[str, str] = {}
        self.constants: dict[str, ast.expr] = {}
        self.array_labels: dict[str, str] = {}
        self.modules: dict[str, str] = {}
        self.label_id = 0
        self.classic_graphics = False
        self.control_depth = 0
        self.assigned: set[str] = set()
        self.raw_helpers: set[str] = set()
        self.functions: dict[str, ast.FunctionDef] = {}
        self.pending_functions: list[str] = []
        self.emitted_functions: set[str] = set()
        self.prelude: dict[str, ast.FunctionDef] = {}
        self.current: ast.FunctionDef | None = None
        self.locals: set[str] = set()
        self.module_names: set[str] = set()
        self.global_writes: set[str] = set()
        self.loops: list[tuple[str, str]] = []
        self.string_labels: dict[str, str] = {}
        self.appvar_labels: dict[str, str] = {}
        self.named_constants: dict[str, ast.expr] = {}
        self.asm_functions: dict[str, tuple[str, list[str], str]] = {}
        self.asm_modules: dict[Path, str] = {}
        self.folding: set[str] = set()
        self.fold_names = False

    def emit(self, line: str = "") -> None:
        self.lines.append(line)

    def label(self, stem: str) -> str:
        self.label_id += 1
        return f"_{stem}_{self.label_id}"

    def directive(self, kind: str) -> str:
        return ("." if self.target == "classic" else "") + kind

    def byte_literal(self, value: int) -> str:
        return f"0{value:02X}h" if self.target == "classic" else f"${value:02X}"

    def data_bytes(self, label: str, values: list[int], chunk_size: int = 32) -> None:
        """Emit byte data on short assembler lines for large assets and strings."""
        for offset in range(0, len(values), chunk_size):
            chunk = ",".join(self.byte_literal(value & 0xFF)
                             for value in values[offset:offset + chunk_size])
            prefix = f"{label}: " if offset == 0 else ""
            self.data.append(f"{prefix}{self.directive('db')} {chunk}")

    def char_buffer_label(self) -> str:
        """A 2-byte buffer holding one character and its terminator, for graphics.char()."""
        if not getattr(self, "_char_buffer", None) or self._char_buffer[0] is not self.data:
            label = self.label("char")
            self.data.append(f"{label}: {self.directive('db')} 0,0")
            self._char_buffer = (self.data, label)
        return self._char_buffer[1]

    def string_label(self, text: str, purpose: str = "string") -> str:
        """Return a label for a NUL-terminated ASCII string, sharing duplicates."""
        if "\0" in text:
            raise CompileError(f"{purpose} cannot contain NUL characters")
        try:
            encoded = text.encode("ascii") + b"\0"
        except UnicodeEncodeError as exc:
            raise CompileError(f"{purpose} supports ASCII strings only") from exc
        if text not in self.string_labels:
            self.string_labels[text] = self.label("str")
            self.data_bytes(self.string_labels[text], list(encoded))
        return self.string_labels[text]

    def integer_literal(self, value: int) -> int:
        """Encode constants using the target's native integer width."""
        return value & (0xFFFFFF if self.target == "ce" else 0xFFFF)

    @property
    def integer_width(self) -> int:
        return 24 if self.target == "ce" else 16

    @property
    def integer_bounds(self) -> tuple[int, int]:
        return -(1 << (self.integer_width - 1)), (1 << (self.integer_width - 1)) - 1

    @property
    def screen(self) -> tuple[int, int]:
        return (320, 240) if self.target == "ce" else (96, 64)

    def _scoped(self, name: str) -> str:
        return f"{self.current.name}.{name}" if self.current is not None and name in self.locals else name

    def variable(self, name: str) -> str:
        if not name.isidentifier():
            raise CompileError(f"invalid variable name: {name}")
        key = self._scoped(name)
        if key not in self.variables:
            self.variables[key] = f"var_{len(self.variables)}"
        return self.variables[key]

    def mark_assigned(self, name: str) -> None:
        self.assigned.add(name)

    def block(self, statements: list[ast.stmt]) -> None:
        self.control_depth += 1
        try:
            for child in statements:
                self.statement(child)
        finally:
            self.control_depth -= 1

    def _prepare_functions(self, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                if node.name in self.functions:
                    raise CompileError(f"line {node.lineno}: function {node.name}() is defined twice")
                if node.name in _BUILTIN_FUNCTIONS or node.name.startswith(("_tipy_", "_rt_")):
                    raise CompileError(f"line {node.lineno}: {node.name} is a reserved function name")
                if not node.name.isascii():
                    raise CompileError(f"line {node.lineno}: function names must be ASCII")
                arguments = node.args
                if arguments.vararg or arguments.kwarg or arguments.kwonlyargs or arguments.posonlyargs:
                    raise CompileError(f"line {node.lineno}: {node.name}() may only use plain parameters")
                self.functions[node.name] = node
        self.module_names = _store_names(tree.body)
        for function in self.functions.values():
            for sub in ast.walk(function):
                if isinstance(sub, ast.Global):
                    written = _store_names(function.body)
                    self.global_writes.update(name for name in sub.names if name in written)
        self._collect_named_constants(tree)
        self._reject_recursion()

    def _collect_named_constants(self, tree: ast.Module) -> None:
        """A module name assigned exactly once can be used wherever a constant is needed."""
        counts: dict[str, int] = {}
        stack: list[ast.AST] = list(tree.body)
        while stack:
            node = stack.pop()
            if isinstance(node, ast.FunctionDef):
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                counts[node.id] = counts.get(node.id, 0) + 1
            stack.extend(ast.iter_child_nodes(node))
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and counts.get(node.targets[0].id) == 1 and node.targets[0].id not in self.global_writes
                    and not self._is_aggregate(node.value)):
                self.named_constants[node.targets[0].id] = node.value

    def _reject_recursion(self) -> None:
        """Function variables are static, so a function cannot re-enter itself."""
        graph = {name: _called_names(node) & set(self.functions) for name, node in self.functions.items()}

        def visit(name: str, path: tuple[str, ...]) -> None:
            if name in path:
                cycle = " -> ".join((*path[path.index(name):], name))
                line = self.functions[name].lineno
                raise CompileError(f"line {line}: recursion is not supported on assembly targets ({cycle}); "
                                   "use a loop, or the flash-app backend")
            for callee in graph[name]:
                visit(callee, (*path, name))

        for name in graph:
            visit(name, ())

    def compile(self, source: str) -> str:
        # Compiler instances are reusable. Clear per-source state before even
        # parsing so a failed compile cannot contaminate the next request.
        self._reset()
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise CompileError(f"line {exc.lineno}: {exc.msg}") from exc
        for node in prelude_tree(self.spec).body:
            if isinstance(node, ast.FunctionDef):
                self.prelude[node.name] = node
            elif isinstance(node, ast.Assign):
                self.constants[node.targets[0].id] = node.value
        self._prepare_functions(tree)
        self.classic_graphics = self.target == "classic" and any(
            (isinstance(node, ast.Import) and any(alias.name == "ti84.graphics" for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "ti84"
                and any(alias.name == "graphics" for alias in node.names))
            for node in ast.walk(tree)
        )
        # On CE, a program that draws leaves the home screen to be redrawn on exit,
        # unless graphics.end() already did it; text printed afterwards then stays.
        self.screen_flag = self.target == "ce" and any(
            (isinstance(node, ast.Import) and any(alias.name in ("ti84.graphics", "ti84.sprite") for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "ti84"
                and any(alias.name in ("graphics", "sprite") for alias in node.names))
            for node in ast.walk(tree)
        )
        # ti84.usb and ti84.serial drive the CE's USB controller, which goes back to
        # the OS when the program exits.
        imported = {alias.name.removeprefix("ti84.") for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {alias.name for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module == "ti84" for alias in node.names}
        self.uses_usb = self.target == "ce" and bool(imported & {"usb", "serial"})
        self.emit(f"; Generated by TIpy-asm for {self.program}")
        if self.target == "classic":
            self.emit("; Target: TI-83+/TI-84 Plus Z80, TASM-style syntax")
            self.emit('#include "ti83plus.inc"')
            self.emit(".org userMem-2")
            self.emit(".db t2ByteTok, tAsmCmp")
            self.emit(".dw start")
        else:
            self.emit("; Target: TI-84 Plus CE eZ80, fasmg TI executable format")
            self.emit("include 'include/ez80.inc'")
            self.emit("include 'include/tiformat.inc'")
            self.emit("include 'include/ti84pceg.inc'")
            self.emit(f"format ti executable '{self.program}'")
        self.emit("start:")
        # exit() and failed library calls can leave from inside any function.
        self.emit("    ld (_rt_saved_sp),sp")
        if self.screen_flag:
            self.emit("    ld a,1")
            self.emit("    ld (_rt_screen_used),a")
        if self.classic_graphics:
            # TI's SDK says GrBufClr/GrBufCpy cover only the active split
            # region. Save both the five YOffset screen attributes and the
            # graphics flags before temporarily switching to normal mode.
            self.emit("    ld hl,YOffset")
            self.emit("    ld de,_gfx_saved_split_state")
            self.emit("    ld bc,5")
            self.emit("    ldir")
            self.emit("    ld a,(iy+sGrFlags)")
            self.emit("    ld (de),a")
            self.emit("    res grfSplit,(iy+sGrFlags)")
            self.emit("    res vertSplit,(iy+sGrFlags)")
            self.emit("    bcall(_SetNorm_Vals)")
            self.emit("    set grfSplitOverride,(iy+sGrFlags)")
        for stmt in tree.body:
            self.statement(stmt)
        self.emit("program_exit:")
        self.emit("    ld sp,(_rt_saved_sp)")
        if self.target == "ce":
            if self.uses_usb:
                # The USB controller must go back to the OS before the program returns.
                self.use_helper("_rt_usb_end")
                self.emit("    call _rt_usb_end")
            if self.screen_flag:
                self.emit("    ld a,(_rt_screen_used)")
                self.emit("    or a,a")
                self.emit("    jr z,_rt_exit_keep_text")
                self.emit("    call ti.ClrScrn")
                self.emit("    call ti.HomeUp")
                self.emit("_rt_exit_keep_text:")
            self.emit("    ld a,ti.lcdBpp16")
            self.emit("    ld (ti.mpLcdCtrl),a")
            self.emit("    call ti.DrawStatusBar")
            self.emit("    ei")
            self.emit("    ret")
        else:
            if self.classic_graphics:
                self.emit("    res grfSplitOverride,(iy+sGrFlags)")
                self.emit("    ld de,YOffset")
                self.emit("    ld hl,_gfx_saved_split_state")
                self.emit("    ld bc,5")
                self.emit("    ldir")
                self.emit("    ld a,(hl)")
                self.emit("    ld (iy+sGrFlags),a")
            self.emit("    ret")
        self._emit_functions()
        code, runtime_data = render(self.raw_helpers, self.spec)
        if code:
            self.emit("\n; Runtime helpers")
            self.lines.extend(code)
        for path, text in self.asm_modules.items():
            self.emit(f"\n; Assembly from {path.name}")
            self.lines.extend(text.splitlines())
        self.emit("\n; Program data")
        self.emit(self.spec.word("_rt_saved_sp"))
        if self.screen_flag:
            self.emit("_rt_screen_used: db 0")
        self.lines.extend(runtime_data)
        if self.data:
            self.lines.extend(self.data)
        if self.variables:
            width = "24-bit" if self.target == "ce" else "16-bit"
            self.emit(f"\n; {width} signed integer variables")
            for label in self.variables.values():
                self.emit(self.spec.word(label))
        if self.classic_graphics:
            self.emit("\n; Saved TI split-screen attributes and graphics flags")
            self.emit("_gfx_saved_split_state: .db 0,0,0,0,0,0")
        return "\n".join(self.lines) + "\n"

    # ------------------------------------------------------------ functions
    def _request_function(self, name: str) -> None:
        if name not in self.emitted_functions and name not in self.pending_functions:
            self.pending_functions.append(name)

    def _emit_functions(self) -> None:
        # User functions are always emitted so their errors are always reported.
        for name in self.functions:
            self._request_function(name)
        while self.pending_functions:
            name = self.pending_functions.pop(0)
            self.emitted_functions.add(name)
            self._emit_function(self.functions.get(name) or self.prelude[name])

    def _emit_function(self, node: ast.FunctionDef) -> None:
        written = _store_names(node.body)
        declared = {name for sub in ast.walk(node) if isinstance(sub, ast.Global) for name in sub.names}
        self.global_writes |= declared & written
        parameters = [arg.arg for arg in node.args.args]
        self.current = node
        self.locals = (written | set(parameters)) - declared
        self.assigned = set(parameters)
        self.control_depth = 1
        self.loops = []
        self.emit(f"\n_fn_{node.name}:")
        try:
            for statement in node.body:
                self.statement(statement)
            self.emit("    ld hl,0")
            self.emit("    ret")
        finally:
            self.current = None
            self.locals = set()
            self.control_depth = 0

    def _bind_arguments(self, node: ast.Call, function: ast.FunctionDef) -> list[ast.expr]:
        parameters = [arg.arg for arg in function.args.args]
        if any(keyword.arg is None for keyword in node.keywords) or any(isinstance(a, ast.Starred) for a in node.args):
            raise CompileError(f"{function.name}() cannot use * or ** arguments")
        if len(node.args) > len(parameters):
            raise CompileError(f"{function.name}() takes {len(parameters)} argument(s), got {len(node.args)}")
        bound: dict[str, ast.expr] = dict(zip(parameters, node.args))
        for keyword in node.keywords:
            if keyword.arg not in parameters:
                raise CompileError(f"{function.name}() has no parameter named {keyword.arg!r}")
            if keyword.arg in bound:
                raise CompileError(f"{function.name}() got {keyword.arg!r} more than once")
            bound[keyword.arg] = keyword.value
        defaults = function.args.defaults
        for name, default in zip(parameters[len(parameters) - len(defaults):], defaults):
            bound.setdefault(name, default)
        missing = [name for name in parameters if name not in bound]
        if missing:
            raise CompileError(f"{function.name}() is missing argument(s): {', '.join(missing)}")
        return [bound[name] for name in parameters]

    def _store_arguments(self, values: list[ast.expr], labels: list[str]) -> None:
        """Evaluate every value, then store them, so nested calls cannot clobber one."""
        if all(self._is_simple(value) for value in values):
            for value, label in zip(values, labels):
                self.expression(value)
                self.emit(f"    ld ({label}),hl")
            return
        for value in values:
            self.expression(value)
            self.emit("    push hl")
        for label in reversed(labels):
            self.emit("    pop hl")
            self.emit(f"    ld ({label}),hl")

    def _is_simple(self, node: ast.expr) -> bool:
        return isinstance(node, (ast.Name, LabelRef)) or self.constant_integer(node) is not None

    def call_function(self, name: str, arguments: list[ast.expr] | None = None, node: ast.Call | None = None) -> None:
        """Call a user or prelude function, leaving its return value in HL."""
        function = self.functions.get(name) or self.prelude[name]
        self._request_function(name)
        values = arguments if arguments is not None else self._bind_arguments(node, function)
        saved_current, saved_locals = self.current, self.locals
        labels = []
        self.current, self.locals = function, {arg.arg for arg in function.args.args}
        try:
            labels = [self.variable(arg.arg) for arg in function.args.args]
        finally:
            self.current, self.locals = saved_current, saved_locals
        if len(values) != len(labels):
            raise CompileError(f"{name}() takes {len(labels)} argument(s), got {len(values)}")
        self._store_arguments(values, labels)
        self.emit(f"    call _fn_{name}")

    def use_helper(self, name: str) -> None:
        self.raw_helpers.add(name)

    def call_raw(self, name: str, arguments: list[ast.expr]) -> None:
        """Call a hand-written runtime routine, leaving its result in HL."""
        if len(arguments) != RAW[name].args or len(arguments) > MAX_RAW_ARGS:
            raise CompileError(f"internal error: {name} takes {RAW[name].args} arguments")
        self.use_helper(name)
        self._store_arguments(arguments, [f"_rt_a{index}" for index in range(len(arguments))])
        self.emit(f"    call {name}")

    def call_named(self, node: ast.Call) -> None:
        """Compile a call to a plain name: a builtin, a user function, or a runtime routine."""
        name = node.func.id
        if name in self.functions:
            self.call_function(name, node=node)
        elif name in self.asm_functions:
            self._call_asm(name, node)
        elif name == "abs" and len(node.args) == 1 and not node.keywords:
            self.expression(node.args[0])
            self.use_helper("_rt_abs")
            self.emit("    call _rt_abs")
        elif name in ("min", "max") and len(node.args) >= 2 and not node.keywords:
            result = node.args[0]
            for value in node.args[1:]:
                result = ast.Call(func=ast.Name(id=f"_tipy_{name}", ctx=ast.Load()), args=[result, value], keywords=[])
            self.expression(result)
        elif name == "exit" and not node.args and not node.keywords:
            self.emit("    jp program_exit")
        elif name in RAW and self.current is not None and self.current.name in self.prelude:
            self.call_raw(name, node.args)
        elif name in self.prelude:
            self.call_function(name, list(node.args))
        else:
            candidates = [*self.functions, *_BUILTIN_FUNCTIONS]
            match = difflib.get_close_matches(name, candidates, n=1)
            hint = f"; did you mean {match[0]}()?" if match else ""
            raise CompileError(f"unknown function {name}(){hint}")

    # ------------------------------------------------------ assembly modules
    def _asm_path(self, module: str) -> Path | None:
        """Find name.<target>.asm, name.<target>.s, name.asm, or name.s."""
        base = self.source_dir.joinpath(*module.split("."))
        for suffix in (f".{self.target}.asm", f".{self.target}.s", ".asm", ".s"):
            candidate = base.parent / (base.name + suffix)
            if candidate.is_file():
                return candidate
        return None

    def _import_asm(self, node: ast.ImportFrom) -> None:
        """Make the routines an assembly file declares callable like functions."""
        module = node.module or ""
        path = self._asm_path(module) if self.source_dir is not None and not node.level else None
        if path is None:
            raise CompileError(f"line {node.lineno}: cannot import from {module}: expected {module}.py, "
                               f"{module}.asm, or {module}.s next to the main file")
        if self.control_depth or self.current is not None:
            raise CompileError("assembly imports must be at module scope")
        exports = self._asm_exports(path)
        names = list(exports) if any(alias.name == "*" for alias in node.names) else [alias.name for alias in node.names]
        aliases = {alias.name: alias.asname for alias in node.names}
        for name in names:
            if name not in exports:
                raise CompileError(f"{path.name} does not declare {name}; add a line such as "
                                   f"'; tipy: def {name}(a, b)' above its label")
            python_name = aliases.get(name) or name
            if python_name in self.functions:
                raise CompileError(f"{python_name} is both a Python function and an assembly routine")
            self.asm_functions[python_name] = (name, exports[name], path.name)

    def _asm_exports(self, path: Path) -> dict[str, list[str]]:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CompileError(f"cannot read {path}: {exc}") from exc
        exports: dict[str, list[str]] = {}
        for match in _ASM_EXPORT.finditer(text):
            name = match.group(1)
            parameters = [part.strip() for part in match.group(2).split(",") if part.strip()]
            line = text.count("\n", 0, match.start()) + 1
            where = f"{path.name} line {line}"
            if name.startswith("_") or name.startswith("var_") or name in _RESERVED_LABELS:
                raise CompileError(f"{where}: {name} would clash with TIpy-asm's own labels; rename it")
            if len(parameters) > len(_ASM_REGISTERS):
                raise CompileError(f"{where}: {name}() takes at most 3 parameters, passed in HL, DE, and BC")
            if len(set(parameters)) != len(parameters) or not all(part.isidentifier() for part in parameters):
                raise CompileError(f"{where}: {name}() needs distinct plain parameter names")
            if not re.search(rf"^[ \t]*{re.escape(name)}(?:[ \t]*:|[ \t]|$)", text, re.MULTILINE):
                raise CompileError(f"{where}: {name} is declared but has no label in {path.name}")
            exports[name] = parameters
        if not exports:
            raise CompileError(f"{path.name} declares no routines; add a line such as '; tipy: def name(a, b)'")
        self.asm_modules.setdefault(path, text)
        return exports

    def _call_asm(self, name: str, node: ast.Call) -> None:
        """Arguments go in HL, DE, and BC; the routine leaves its result in HL."""
        label, parameters, filename = self.asm_functions[name]
        if any(isinstance(arg, ast.Starred) for arg in node.args) or any(kw.arg is None for kw in node.keywords):
            raise CompileError(f"{name}() cannot use * or ** arguments")
        if len(node.args) > len(parameters):
            raise CompileError(f"{name}() from {filename} takes {len(parameters)} argument(s), got {len(node.args)}")
        bound = dict(zip(parameters, node.args))
        for keyword in node.keywords:
            if keyword.arg not in parameters or keyword.arg in bound:
                raise CompileError(f"{name}() got an unexpected or repeated argument {keyword.arg!r}")
            bound[keyword.arg] = keyword.value
        missing = [parameter for parameter in parameters if parameter not in bound]
        if missing:
            raise CompileError(f"{name}() is missing argument(s): {', '.join(missing)}")
        values = [bound[parameter] for parameter in parameters]
        if len(values) == 1:
            self.expression(values[0])
        elif values:
            for value in values:
                self.expression(value)
                self.emit("    push hl")
            for register in reversed(_ASM_REGISTERS[:len(values)]):
                self.emit(f"    pop {register}")
        self.emit(f"    call {label}")

    # ----------------------------------------------------------- statements
    def statement(self, node: ast.stmt) -> None:
        """Compile one statement, attaching its source line to any error."""
        try:
            self._statement(node)
        except CompileError as exc:
            message = str(exc)
            if not _LINE_PREFIX.match(message) and hasattr(node, "lineno"):
                raise CompileError(f"line {node.lineno}: {message}") from exc
            raise

    def _assign_name(self, name: str, value: ast.expr) -> None:
        if self.control_depth and name in self.constants and self.current is None:
            raise CompileError("aggregate constants cannot be reassigned inside control flow")
        if self.current is None:
            self.constants.pop(name, None)
        target = self.variable(name)
        self.expression(value)
        self.emit(f"    ld ({target}),hl")
        self.mark_assigned(name)

    def _is_aggregate(self, node: ast.expr) -> bool:
        if isinstance(node, (ast.Tuple, ast.List)):
            return True
        return (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
                and isinstance(node.left, ast.List))

    def _aggregate_value(self, node: ast.expr) -> ast.expr:
        """Expand ``[0] * 10`` into its elements, so an array is always a literal."""
        if isinstance(node, ast.BinOp):
            count = self.required_constant(node.right)
            if count is None or count < 1:
                raise CompileError("array size in [value] * size must be a positive integer constant")
            return ast.List(elts=list(node.left.elts) * count, ctx=ast.Load())
        return node

    def _statement(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Import):
            if self.control_depth:
                raise CompileError("library imports must be declared at module scope")
            for item in node.names:
                library = item.name.removeprefix("ti84.")
                problem = library_error(library, self.target) if item.name.startswith("ti84.") else None
                if problem:
                    raise CompileError(problem)
                if not item.name.startswith("ti84.") or not item.asname:
                    raise CompileError(f"import libraries with 'from ti84 import {library}' "
                                       f"(available: {', '.join(assembly_libraries())})")
                self.modules[item.asname] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module == "ti84":
            if self.control_depth:
                raise CompileError("library imports must be declared at module scope")
            for item in node.names:
                problem = library_error(item.name, self.target)
                if problem:
                    raise CompileError(problem)
                self.modules[item.asname or item.name] = f"ti84.{item.name}"
        elif isinstance(node, ast.ImportFrom):
            self._import_asm(node)
        elif isinstance(node, ast.FunctionDef):
            if self.current is not None or self.control_depth:
                raise CompileError("functions must be defined at module scope")
        elif isinstance(node, ast.Global):
            if self.current is None:
                raise CompileError("global is only meaningful inside a function")
        elif isinstance(node, ast.Return):
            if self.current is None:
                raise CompileError("return outside a function; use exit() to end the program")
            if node.value is None:
                self.emit("    ld hl,0")
            else:
                self.expression(node.value)
            self.emit("    ret")
        elif isinstance(node, ast.Break):
            if not self.loops:
                raise CompileError("break outside a loop")
            self.emit(f"    jp {self.loops[-1][1]}")
        elif isinstance(node, ast.Continue):
            if not self.loops:
                raise CompileError("continue outside a loop")
            self.emit(f"    jp {self.loops[-1][0]}")
        elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Tuple) for target in node.targets):
            self._unpack(node)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and self._is_aggregate(node.value)):
            # Aggregate constants are compile-time data, used by APIs such as
            # graphics.sprite(); they do not occupy calculator RAM by default.
            if self.control_depth:
                raise CompileError("aggregate constants must be declared at module scope")
            self.constants[node.targets[0].id] = self._aggregate_value(node.value)
            self.assigned.discard(node.targets[0].id)
        elif isinstance(node, ast.Assign) and all(isinstance(target, (ast.Name, ast.Subscript)) for target in node.targets):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self._assign_name(node.targets[0].id, node.value)
            elif len(node.targets) == 1:
                self._store_subscript(node.targets[0], node.value)
            else:
                # a = b = value: evaluate once, then store left to right.
                temporary = self.label("chain")
                self.expression(node.value)
                self.emit(f"    ld ({self.variable(temporary)}),hl")
                self.mark_assigned(temporary)
                for target in node.targets:
                    value = ast.Name(id=temporary, ctx=ast.Load())
                    if isinstance(target, ast.Name):
                        self._assign_name(target.id, value)
                    else:
                        self._store_subscript(target, value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                if self._is_aggregate(node.value):
                    if self.control_depth:
                        raise CompileError("aggregate constants must be declared at module scope")
                    self.constants[node.target.id] = self._aggregate_value(node.value)
                else:
                    self._assign_name(node.target.id, node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            self.require_assigned(name, node.lineno)
            if self.control_depth and name in self.constants and self.current is None:
                raise CompileError("aggregate constants cannot be reassigned inside control flow")
            if self.current is None:
                self.constants.pop(name, None)
            target = self.variable(name)
            self._binop(ast.Name(id=name, ctx=ast.Load()), node.op, node.value)
            self.emit(f"    ld ({target}),hl")
            self.mark_assigned(name)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Subscript):
            load = ast.Subscript(value=node.target.value, slice=node.target.slice, ctx=ast.Load())
            self._store_subscript(node.target, ast.BinOp(left=load, op=node.op, right=node.value))
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
              and isinstance(node.value.value, str)):
            # Module and statement docstrings have no runtime effect here.
            return
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            self.call(node.value)
        elif isinstance(node, ast.If):
            self._if(node)
        elif isinstance(node, ast.While):
            if node.orelse:
                raise CompileError("while loops do not support an else clause")
            top, done = self.label("while"), self.label("wend")
            self.emit(top + ":")
            self.condition_false(node.test, done)
            assigned_before = self.assigned.copy()
            self.loops.append((top, done))
            self.block(node.body)
            self.loops.pop()
            self.assigned = assigned_before
            self.emit(f"    jp {top}")
            self.emit(done + ":")
        elif isinstance(node, ast.For):
            self._for(node)
        elif isinstance(node, ast.Pass):
            return
        else:
            raise CompileError(f"line {getattr(node, 'lineno', '?')}: unsupported statement {type(node).__name__}")

    def _unpack(self, node: ast.Assign) -> None:
        if len(node.targets) != 1 or not isinstance(node.value, (ast.Tuple, ast.List)):
            raise CompileError("unpacking needs matching names and values, such as: x, y = y, x")
        names, values = node.targets[0].elts, node.value.elts
        if len(names) != len(values) or not all(isinstance(name, ast.Name) for name in names):
            raise CompileError("unpacking needs the same number of plain names and values")
        for value in values:
            self.expression(value)
            self.emit("    push hl")
        for name in reversed(names):
            self.emit("    pop hl")
            self.emit(f"    ld ({self.variable(name.id)}),hl")
            self.mark_assigned(name.id)

    def _if(self, node: ast.If) -> None:
        test = node.test
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
            # The merged program is always the main module.
            for statement in node.body:
                self.statement(statement)
            return
        otherwise, end = self.label("else"), self.label("endif")
        self.condition_false(test, otherwise)
        assigned_before = self.assigned.copy()
        self.block(node.body)
        assigned_then = self.assigned.copy()
        if node.orelse:
            self.emit(f"    jp {end}")
        self.emit(otherwise + ":")
        self.assigned = assigned_before.copy()
        self.block(node.orelse)
        assigned_else = self.assigned.copy()
        if node.orelse:
            self.emit(end + ":")
        self.assigned = assigned_then & assigned_else
        if isinstance(test, ast.Constant) and isinstance(test.value, bool):
            self.assigned = assigned_then if test.value else assigned_else

    def _for(self, node: ast.For) -> None:
        if (not isinstance(node.target, ast.Name) or not isinstance(node.iter, ast.Call)
                or not isinstance(node.iter.func, ast.Name) or node.iter.func.id != "range"
                or node.iter.keywords or node.orelse or not 1 <= len(node.iter.args) <= 3):
            raise CompileError("for loops support a range() call with 1-3 arguments and no else clause")
        if node.target.id in self.constants:
            raise CompileError("aggregate constants cannot be used as loop targets")
        arguments = node.iter.args
        start_node = arguments[0] if len(arguments) > 1 else ast.Constant(value=0)
        stop_node = arguments[1] if len(arguments) > 1 else arguments[0]
        step = 1
        if len(arguments) == 3:
            step = self.required_constant(arguments[2])
            if step is None:
                raise CompileError("range() step must be an integer constant, so the loop direction is known")
        if step == 0:
            raise CompileError("range() step cannot be zero")
        min_integer, max_integer = self.integer_bounds
        start = self.constant_integer(start_node)
        stop = self.constant_integer(stop_node)
        for literal in (start_node, stop_node):
            if isinstance(literal, ast.Constant) and self.constant_integer(literal) is None:
                raise CompileError(f"range() bounds and step must fit signed {self.integer_width}-bit integers")
        if start is not None and stop is not None:
            if step > 0 and start < stop:
                last = start + ((stop - 1 - start) // step) * step
                overflow = last + step > max_integer
            elif step < 0 and start > stop:
                last = start - ((start - stop - 1) // -step) * -step
                overflow = last + step < min_integer
            else:
                overflow = False
            if overflow:
                raise CompileError(f"{self.target} range() loop may overflow its {self.integer_width}-bit counter")
        assigned_before = self.assigned.copy()
        variable = self.variable(node.target.id)
        # Python evaluates a range's bounds once, before the first iteration.
        if stop is None:
            stop_name = self.label("range_stop")
            self.expression(stop_node)
            self.emit(f"    ld ({self.variable(stop_name)}),hl")
            self.mark_assigned(stop_name)
            limit: ast.expr = ast.Name(id=stop_name, ctx=ast.Load())
        else:
            limit = ast.Constant(value=stop)
        self.expression(start_node)
        self.emit(f"    ld ({variable}),hl")
        self.mark_assigned(node.target.id)
        top, advance, done = self.label("for"), self.label("for_next"), self.label("for_end")
        test = ast.Compare(left=ast.Name(id=node.target.id, ctx=ast.Load()),
                           ops=[ast.Lt() if step > 0 else ast.Gt()], comparators=[limit])
        self.emit(top + ":")
        self.condition_false(test, done)
        self.loops.append((advance, done))
        self.block(node.body)
        self.loops.pop()
        self.emit(advance + ":")
        self.emit(f"    ld hl,({variable})")
        self.emit(f"    ld de,{self.integer_literal(step)}")
        self.emit("    add hl,de")
        self.emit(f"    ld ({variable}),hl")
        self.emit(f"    jp {top}")
        self.emit(done + ":")
        self.assigned = assigned_before | {node.target.id}

    # ----------------------------------------------------------------- arrays
    def _array(self, name: str) -> tuple[str, int]:
        """Return the data label and length of a flat constant integer array."""
        constant = self.constants.get(name)
        if not isinstance(constant, (ast.Tuple, ast.List)):
            raise CompileError(f"{name!r} is not an array; declare it at module scope, "
                               f"such as {name} = (1, 2, 3) or {name} = [0] * 10")
        if name not in self.array_labels:
            label = self.label("array")
            self.array_labels[name] = label
            values: list[int] = []
            for element in constant.elts:
                value = self.required_constant(element)
                if value is None and isinstance(element, ast.Constant) and isinstance(element.value, int):
                    value = element.value
                if value is None:
                    raise CompileError(f"array {name!r} may only contain integer constants")
                encoded = self.integer_literal(value)
                values.extend((encoded >> (8 * index)) & 0xFF for index in range(self.spec.word_bytes))
            self.data_bytes(label, values)
        return self.array_labels[name], len(constant.elts)

    def _element_address(self, node: ast.Subscript) -> None:
        """Leave the address of an array element in HL."""
        if not isinstance(node.value, ast.Name) or isinstance(node.slice, ast.Slice):
            raise CompileError("indexing supports one integer index into a module-level array, such as DATA[i]")
        label, length = self._array(node.value.id)
        index = self.constant_integer(node.slice)
        if index is not None:
            if index < 0:
                index += length
            if not 0 <= index < length:
                raise CompileError(f"index out of range for {node.value.id!r}, which has {length} items")
            self.emit(f"    ld hl,{label}+{index * self.spec.word_bytes}")
            return
        self.expression(node.slice)
        if self.spec.is_ce:
            self.emit("    push hl")
            self.emit("    pop de")
            self.emit("    add hl,hl")
            self.emit("    add hl,de")
        else:
            self.emit("    add hl,hl")
        self.emit(f"    ld de,{label}")
        self.emit("    add hl,de")

    def _store_subscript(self, target: ast.Subscript, value: ast.expr) -> None:
        if isinstance(target.value, ast.Name) and isinstance(self.constants.get(target.value.id), ast.Tuple):
            raise CompileError(f"{target.value.id!r} is a tuple and cannot be changed; declare it as a list")
        self.expression(value)
        self.emit("    push hl")
        self._element_address(target)
        self.emit("    pop de")
        self._store_word_at_hl()

    def _store_word_at_hl(self) -> None:
        if self.spec.is_ce:
            self.emit("    ld (hl),de")
        else:
            self.emit("    ld (hl),e")
            self.emit("    inc hl")
            self.emit("    ld (hl),d")

    def _load_word_from_hl(self) -> None:
        if self.spec.is_ce:
            self.emit("    ld hl,(hl)")
        else:
            self.emit("    ld e,(hl)")
            self.emit("    inc hl")
            self.emit("    ld d,(hl)")
            self.emit("    ex de,hl")

    # ------------------------------------------------------------------ calls
    def _print(self, node: ast.Call) -> None:
        if node.keywords:
            raise CompileError("print() does not support keyword arguments")
        for index, argument in enumerate(node.args):
            if index:
                self.emit(f"    ld hl,{self.string_label(' ')}")
                self.emit(f"    {self.spec.rom('PutS')}")
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                self.emit(f"    ld hl,{self.string_label(argument.value, 'print()')}")
            else:
                self.expression(argument)
                self.use_helper("_rt_itoa")
                self.emit("    call _rt_itoa")
            self.emit(f"    {self.spec.rom('PutS')}")
        self.emit(f"    {self.spec.rom('NewLine')}")

    def call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id == "print":
                self._print(node)
            else:
                self.call_named(node)
            return
        emit_call(self, node)

    # ------------------------------------------------------------ expressions
    def expression(self, node: ast.expr) -> None:
        constant = self.constant_integer(node)
        if constant is not None:
            self.emit(f"    ld hl,{self.integer_literal(constant)}")
        elif isinstance(node, LabelRef):
            self.emit(f"    ld hl,{node.label}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ("print", "exit"):
                    raise CompileError(f"{node.func.id}() does not return a value")
                self.call_named(node)
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                emit_call(self, node, want_value=True)
            else:
                raise CompileError("calls must name a function or a library method")
        elif isinstance(node, ast.Attribute):
            emit_attribute(self, node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            self.emit(f"    ld hl,{int(node.value)}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, int):
            # Literals above the signed range are bit patterns such as 0xFFFF.
            minimum, _ = self.integer_bounds
            if not minimum <= node.value < (1 << self.integer_width):
                raise CompileError(f"integer constants must fit signed {self.integer_width}-bit range")
            self.emit(f"    ld hl,{self.integer_literal(node.value)}")
        elif isinstance(node, ast.Name):
            if node.id in self.constants:
                raise CompileError(
                    f"aggregate constant {node.id!r} can only be indexed or passed to a library that accepts aggregate data"
                )
            self.require_assigned(node.id, getattr(node, "lineno", None))
            self.emit(f"    ld hl,({self.variable(node.id)})")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            self.expression(node.operand)
            self.use_helper("_rt_neg")
            self.emit("    call _rt_neg")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
            self.expression(node.operand)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            # ~x == -x - 1
            self.expression(node.operand)
            self.use_helper("_rt_neg")
            self.emit("    call _rt_neg")
            self.emit("    dec hl")
        elif isinstance(node, ast.BinOp):
            self._binop(node.left, node.op, node.right)
        elif isinstance(node, ast.BoolOp):
            self._boolop(node)
        elif isinstance(node, (ast.Compare, ast.UnaryOp)):
            otherwise, done = self.label("bool_false"), self.label("bool_done")
            self.condition_false(node, otherwise)
            self.emit("    ld hl,1")
            self.emit(f"    jp {done}")
            self.emit(otherwise + ":")
            self.emit("    ld hl,0")
            self.emit(done + ":")
        elif isinstance(node, ast.IfExp):
            otherwise, done = self.label("ifexp_else"), self.label("ifexp_done")
            self.condition_false(node.test, otherwise)
            self.expression(node.body)
            self.emit(f"    jp {done}")
            self.emit(otherwise + ":")
            self.expression(node.orelse)
            self.emit(done + ":")
        elif isinstance(node, ast.Subscript):
            self._element_address(node)
            self._load_word_from_hl()
        else:
            raise CompileError(f"assembly targets do not support {_describe(node)}")

    def _boolop(self, node: ast.BoolOp) -> None:
        """Python's and/or yield one of their operands, not just True or False."""
        done = self.label("boolop_done")
        for value in node.values[:-1]:
            self.expression(value)
            self._test_hl()
            self.emit(f"    jp {'z' if isinstance(node.op, ast.And) else 'nz'},{done}")
        self.expression(node.values[-1])
        self.emit(done + ":")

    def _test_hl(self) -> None:
        """Set the Z flag from HL without changing it; ADD HL,DE leaves Z alone."""
        self.emit("    ld de,0")
        self.emit("    or a")
        self.emit("    sbc hl,de")
        self.emit("    add hl,de")

    def _binop(self, left: ast.expr, op: ast.operator, right: ast.expr) -> None:
        folded = self.constant_integer(ast.BinOp(left=left, op=op, right=right))
        if folded is not None:
            self.emit(f"    ld hl,{self.integer_literal(folded)}")
            return
        if isinstance(op, (ast.FloorDiv, ast.Mod)) and self.constant_integer(right) == 0:
            raise CompileError("division by zero")
        constant_right = self.constant_integer(right)
        if constant_right is not None:
            self.expression(left)
            self.emit(f"    ld de,{self.integer_literal(constant_right)}")
        else:
            self.expression(left)
            self.emit("    push hl")
            self.expression(right)
            self.emit("    ex de,hl")
            self.emit("    pop hl")
        self.binary(op)

    def constant_integer(self, node: ast.expr) -> int | None:
        """Evaluate the supported integer-only expression subset at compile time."""
        minimum, maximum = self.integer_bounds
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value if minimum <= node.value <= maximum else None
        if isinstance(node, ast.Name):
            return self._named_constant(node.id)
        if isinstance(node, (ast.Attribute, ast.Call)):
            value = constant_library(self, node)
            if value is not None and minimum <= value <= maximum:
                return value
            return None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = self.constant_integer(node.operand)
            if (value is None and isinstance(node.operand, ast.Constant)
                    and isinstance(node.operand.value, int) and not isinstance(node.operand.value, bool)
                    and node.operand.value == maximum + 1):
                value = maximum + 1
            return -value if value is not None else None
        if isinstance(node, ast.BinOp):
            left = self.constant_integer(node.left)
            right = self.constant_integer(node.right)
            if left is None or right is None:
                return None
            operators = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.FloorDiv: lambda: left // right if right else None,
                ast.Mod: lambda: left % right if right else None,
                ast.LShift: lambda: left << right if 0 <= right < 64 else None,
                ast.RShift: lambda: left >> right if right >= 0 else None,
                ast.BitAnd: lambda: left & right,
                ast.BitOr: lambda: left | right,
                ast.BitXor: lambda: left ^ right,
            }
            operation = operators.get(type(node.op))
            value = operation() if operation else None
            return value if value is not None and minimum <= value <= maximum else None
        return None

    def required_constant(self, node: ast.expr) -> int | None:
        """Evaluate where only a constant will do, allowing names assigned once.

        Elsewhere such a name stays a variable, so that drawing with it clips at
        runtime just as it does for any other variable.
        """
        self.fold_names = True
        try:
            return self.constant_integer(node)
        finally:
            self.fold_names = False

    def _named_constant(self, name: str) -> int | None:
        value = self.named_constants.get(name)
        if (not self.fold_names or value is None or name in self.folding
                or (self.current is not None and name in self.locals)):
            return None
        # Reading a name before its assignment must stay an error at module level.
        if self.current is None and name not in self.assigned:
            return None
        self.folding.add(name)
        try:
            return self.constant_integer(value)
        finally:
            self.folding.discard(name)

    def binary(self, op: ast.operator) -> None:
        """Apply an operator to HL (left) and DE (right), leaving the result in HL."""
        if isinstance(op, ast.Add):
            self.emit("    add hl,de")
        elif isinstance(op, ast.Sub):
            self.emit("    or a")
            self.emit("    sbc hl,de")
        elif isinstance(op, ast.FloorDiv):
            self.use_helper("_rt_divmod")
            self.emit("    call _rt_divmod")
        elif isinstance(op, ast.Mod):
            self.use_helper("_rt_divmod")
            self.emit("    call _rt_divmod")
            self.emit("    ex de,hl")
        else:
            helpers = {ast.Mult: "_rt_mul", ast.BitAnd: "_rt_and", ast.BitOr: "_rt_or",
                       ast.BitXor: "_rt_xor", ast.LShift: "_rt_shl", ast.RShift: "_rt_sar"}
            helper = helpers.get(type(op))
            if helper is None:
                raise CompileError(f"assembly targets do not support {_describe(ast.BinOp(left=None, op=op, right=None))}")
            self.use_helper(helper)
            self.emit(f"    call {helper}")

    def require_assigned(self, name: str, line: int | None) -> None:
        if name in self.assigned or name in self.global_writes:
            return
        if self.current is not None and name not in self.locals and name in self.module_names:
            return
        location = f"line {line}: " if line is not None else ""
        if self.current is not None and name in self.locals and name in self.module_names:
            raise CompileError(f"{location}variable {name!r} is local to {self.current.name}() because it is "
                               f"assigned there; add 'global {name}' to change the module variable")
        if self.current is None and name not in self.module_names:
            candidates = [*self.module_names, *self.modules]
            match = difflib.get_close_matches(name, candidates, n=1)
            hint = f"; did you mean {match[0]!r}?" if match else ""
            raise CompileError(f"{location}variable {name!r} is not defined{hint}")
        raise CompileError(f"{location}variable {name!r} may be read before assignment")

    def condition_true(self, node: ast.expr, true_label: str) -> None:
        fallthrough = self.label("cond_false")
        self.condition_false(node, fallthrough)
        self.emit(f"    jp {true_label}")
        self.emit(fallthrough + ":")

    def condition_false(self, node: ast.expr, false_label: str) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            if not node.value:
                self.emit(f"    jp {false_label}")
            return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self.condition_true(node.operand, false_label)
            return
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    self.condition_false(value, false_label)
            else:
                body = self.label("cond_true")
                for value in node.values[:-1]:
                    self.condition_true(value, body)
                self.condition_false(node.values[-1], false_label)
                self.emit(body + ":")
            return
        if isinstance(node, ast.Compare) and len(node.ops) > 1:
            operands = [node.left, *node.comparators]
            if not all(self._is_simple(operand) for operand in operands):
                raise CompileError("chained comparisons need plain variables or constants; store other values first")
            for index, op in enumerate(node.ops):
                self.condition_false(ast.Compare(left=operands[index], ops=[op],
                                                 comparators=[operands[index + 1]]), false_label)
            return
        if isinstance(node, ast.Compare):
            op = node.ops[0]
            if not isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
                raise CompileError("conditions support ==, !=, <, <=, >, and >=")
            self.expression(node.left)
            right = self.constant_integer(node.comparators[0])
            if right is not None:
                self.emit(f"    ld de,{self.integer_literal(right)}")
            else:
                self.emit("    push hl")
                self.expression(node.comparators[0])
                self.emit("    ex de,hl")
                self.emit("    pop hl")
            self.emit("    or a")
            self.emit("    sbc hl,de")
            if isinstance(op, ast.Eq):
                self.emit(f"    jp nz,{false_label}")
            elif isinstance(op, ast.NotEq):
                self.emit(f"    jp z,{false_label}")
            else:
                # Python integer comparisons are signed. S XOR P/V determines
                # the signed result after subtraction; carry alone is unsigned.
                overflow = self.label("cmp_overflow")
                done = self.label("cmp_done")
                self.emit(f"    jp pe,{overflow}")
                if isinstance(op, ast.Lt):
                    self.emit(f"    jp p,{false_label}")
                    self.emit(f"    jp {done}")
                    self.emit(overflow + ":")
                    self.emit(f"    jp p,{done}")
                    self.emit(f"    jp {false_label}")
                elif isinstance(op, ast.Gt):
                    self.emit(f"    jp z,{false_label}")
                    self.emit(f"    jp m,{false_label}")
                    self.emit(f"    jp {done}")
                    self.emit(overflow + ":")
                    self.emit(f"    jp m,{done}")
                    self.emit(f"    jp {false_label}")
                elif isinstance(op, ast.LtE):
                    self.emit(f"    jp m,{done}")
                    self.emit(f"    jp z,{done}")
                    self.emit(f"    jp {false_label}")
                    self.emit(overflow + ":")
                    self.emit(f"    jp p,{done}")
                    self.emit(f"    jp {false_label}")
                else:  # ast.GtE
                    self.emit(f"    jp m,{false_label}")
                    self.emit(f"    jp {done}")
                    self.emit(overflow + ":")
                    self.emit(f"    jp p,{false_label}")
                self.emit(done + ":")
            return
        # Any other value follows Python truthiness: zero is false.
        self.expression(node)
        self.emit("    ld de,0")
        self.emit("    or a")
        self.emit("    sbc hl,de")
        self.emit(f"    jp z,{false_label}")
