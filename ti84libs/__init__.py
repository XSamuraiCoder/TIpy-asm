"""Built-in TI-84 libraries shipped separately from the compiler core."""

from __future__ import annotations

import ast
import difflib

from ti84asm.errors import CompileError

from . import color, font, graphics, keyboard, math as mathlib, random as randomlib, serial, sprite, storage, usb
from .api import API, FLASH_ONLY, NOT_IMPLEMENTED, REPLACED

_HANDLERS = {
    "graphics": graphics.emit_call,
    "keyboard": keyboard.emit_call,
    "math": mathlib.emit_expression,
    "random": randomlib.emit_call,
    "storage": storage.emit_call,
    "file": storage.emit_call,
    "sprite": sprite.emit_call,
    "color": color.emit_call,
    "usb": usb.emit_call,
    "font": font.emit_call,
    "serial": serial.emit_call,
}


def assembly_libraries() -> list[str]:
    return [name for name in API if name not in FLASH_ONLY]


def library_error(name: str, target: str) -> str | None:
    """Explain why a library cannot be imported on an assembly target, or return None."""
    if name in REPLACED:
        return REPLACED[name]
    if name in FLASH_ONLY:
        return f"ti84.{name} is available to the Flash App backend, not standalone assembly; use the flash-app command"
    if name not in API:
        match = difflib.get_close_matches(name, API, n=1)
        hint = f"; did you mean {match[0]}?" if match else ""
        return f"unknown ti84 library: {name}{hint} (available: {', '.join(assembly_libraries())})"
    return None


def _library_of(compiler, node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        module = compiler.modules.get(node.id)
        if module:
            return module.removeprefix("ti84.")
    return None


def emit_call(compiler, node: ast.Call, want_value: bool = False) -> None:
    """Validate a library call against the API table, then compile it."""
    if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
        raise CompileError("calls must name a function or a library method, such as graphics.pixel(x, y)")
    library = _library_of(compiler, node.func.value)
    method_name = node.func.attr
    if library is None:
        base = node.func.value.id
        if base in API:
            raise CompileError(f"add 'from ti84 import {base}' before calling {base}.{method_name}()")
        raise CompileError(f"{base} is not an imported library, so {base}.{method_name}() cannot be called")
    method = API[library].get(method_name)
    if method is None:
        if library in NOT_IMPLEMENTED:
            raise CompileError(f"{library}.{method_name}(): {NOT_IMPLEMENTED[library]}")
        match = difflib.get_close_matches(method_name, API[library], n=1)
        hint = f"did you mean {library}.{match[0]}()? " if match else ""
        raise CompileError(f"{library} has no method {method_name}(); {hint}run 'tipy-asm api {library}' to list them")
    if compiler.target not in method.targets:
        from .api import flash_available

        where = [*method.targets, *(("the flash-app backend",) if flash_available(library, method_name) else ())]
        detail = f"available on: {', '.join(where)}" if where else "it is not implemented yet"
        note = f" ({method.note})" if method.note else ""
        raise CompileError(f"{library}.{method_name}() is not available on the {compiler.target} target; {detail}{note}")
    if want_value and not method.returns:
        raise CompileError(f"{library}.{method_name}() does not return a value")
    _HANDLERS[library](compiler, node)


def constant_library(compiler, node: ast.expr) -> int | None:
    """Return the compile-time value of a library constant or constant call."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        library = _library_of(compiler, node.func.value)
        return color.constant_call(compiler, node) if library == "color" else None
    if not isinstance(node, ast.Attribute):
        return None
    library = _library_of(compiler, node.value)
    if library == "graphics":
        return graphics.constant(compiler, node.attr)
    if library == "keyboard":
        return keyboard.key_code(node.attr)
    if library == "font" and font.constant(node.attr) is not None:
        return font.constant(node.attr)
    if library in ("color", "font"):
        return color.constant(compiler, node.attr)
    if library == "usb":
        return usb.constant(node.attr)
    return None


def emit_attribute(compiler, node: ast.Attribute) -> None:
    value = constant_library(compiler, node)
    if value is not None:
        compiler.emit(f"    ld hl,{compiler.integer_literal(value)}")
        return
    library = _library_of(compiler, node.value)
    if library is None:
        raise CompileError("attribute access is only supported for library constants, such as graphics.RED")
    if library == "keyboard":
        raise CompileError(f"unknown keyboard key: {node.attr}")
    raise CompileError(f"unknown {library} constant: {node.attr}")
