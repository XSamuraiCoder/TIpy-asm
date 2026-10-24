"""Persistent byte storage using TI AppVars."""

import ast
import re

from ti84asm.errors import CompileError
from .util import literal_integer


def _os_call(compiler, routine: str) -> None:
    compiler.emit(f"    bcall(_{routine})" if compiler.target == "classic" else f"    call ti.{routine}")


def _appvar_name(compiler, name: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", name):
        raise CompileError("AppVar names must be 1-8 uppercase ASCII letters/digits")
    label = compiler.label("appvar")
    bytestr = ",".join(compiler.byte_literal(ord(ch)) for ch in name + "\0")
    object_type = "AppVarObj" if compiler.target == "classic" else "ti.AppVarObj"
    compiler.data.append(f"{label}: {compiler.directive('db')} {object_type},{bytestr}")
    return label


def _emit_find_appvar(compiler, name: str) -> tuple[str, str]:
    label = _appvar_name(compiler, name)
    error, done = compiler.label("appvar_error"), compiler.label("appvar_done")
    compiler.emit(f"    ld hl,{label}")
    _os_call(compiler, "Mov9ToOP1")
    _os_call(compiler, "ChkFindSym")
    compiler.emit(f"    jp c,{error}")
    compiler.emit("    ld a,b")
    compiler.emit("    or a")
    compiler.emit(f"    jp nz,{error} ; archived AppVars must be unarchived")
    return error, done


def _emit_byte_address(compiler, name: str, offset: int, value: int | None = None,
                      value_label: str | None = None) -> None:
    error, done = _emit_find_appvar(compiler, name)
    compiler.emit("    ex de,hl ; HL points to AppVar length")
    compiler.emit("    ld e,(hl)")
    compiler.emit("    inc hl")
    compiler.emit("    ld d,(hl) ; DE = AppVar byte length")
    compiler.emit("    inc hl")
    compiler.emit("    inc hl ; HL points to data")
    compiler.emit("    push hl")
    compiler.emit(f"    ld hl,{offset}")
    compiler.emit("    or a")
    compiler.emit("    sbc hl,de")
    compiler.emit("    pop hl")
    compiler.emit(f"    jp nc,{error} ; reject out-of-range offsets")
    compiler.emit(f"    ld de,{offset}")
    compiler.emit("    add hl,de")
    if value is not None:
        compiler.emit(f"    ld a,{compiler.byte_literal(value)}")
        compiler.emit("    ld (hl),a")
    elif value_label is not None:
        compiler.emit(f"    ld a,({value_label})")
        compiler.emit("    ld (hl),a")
    compiler.emit(f"    jp {done}")
    compiler.emit(error + ":")
    compiler.emit("    jp program_exit" if compiler.target == "ce" else "    ret")
    compiler.emit(done + ":")


def emit_call(compiler, node: ast.Call) -> None:
    def appvar_arg() -> str:
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            raise CompileError("storage methods require an AppVar name string as the first argument")
        return node.args[0].value.upper()

    if node.keywords:
        raise CompileError("storage methods use positional arguments only")
    if node.func.attr == "create" and len(node.args) == 2:
        name = appvar_arg()
        size = literal_integer(node.args[1], "AppVar size")
        if size < 1:
            raise CompileError("AppVar size must be at least 1 byte")
        label = _appvar_name(compiler, name)
        created = compiler.label("appvar_created")
        compiler.emit(f"    ld hl,{label}")
        _os_call(compiler, "Mov9ToOP1")
        _os_call(compiler, "ChkFindSym")
        compiler.emit(f"    jp nc,{created}")
        compiler.emit(f"    ld hl,{label}")
        _os_call(compiler, "Mov9ToOP1")
        compiler.emit(f"    ld hl,{size}")
        _os_call(compiler, "CreateAppVar")
        compiler.emit("    ex de,hl ; HL points to AppVar length")
        compiler.emit("    inc hl")
        compiler.emit("    inc hl ; HL points to AppVar data")
        compiler.emit(f"    ld bc,{size}")
        compiler.emit("    xor a")
        _os_call(compiler, "MemSet")
        compiler.emit(created + ":")
    elif node.func.attr == "write_byte" and len(node.args) == 3:
        name = appvar_arg()
        offset = literal_integer(node.args[1], "AppVar offset")
        if isinstance(node.args[2], ast.Constant) and isinstance(node.args[2].value, int) \
                and not isinstance(node.args[2].value, bool):
            value = literal_integer(node.args[2], "byte value", allow_unsigned=True)
        else:
            # Runtime values are kept in a scratch word while the OS locates
            # the AppVar, then their low byte is written to the requested slot.
            value = None
        if value is not None:
            if value > 255:
                raise CompileError("byte value must be in the range 0..255")
            _emit_byte_address(compiler, name, offset, value)
        else:
            compiler.expression(node.args[2])
            scratch = compiler.label("storage_value")
            compiler.emit(f"    ld ({scratch}),hl")
            compiler.data.append(
                f"{scratch}: " + ("db 0,0,0" if compiler.target == "ce" else ".dw 0")
            )
            _emit_byte_address(compiler, name, offset, value_label=scratch)
    elif node.func.attr == "read_byte" and len(node.args) == 2:
        raise CompileError("storage.read_byte() must be assigned to a variable")
    else:
        raise CompileError("storage supports create(name, size), read_byte(name, offset), and write_byte(name, offset, value)")


def emit_read_expression(compiler, node: ast.Call) -> None:
    if len(node.args) != 2 or node.keywords:
        raise CompileError("read_byte() takes an AppVar name and byte offset")
    if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        raise CompileError("read_byte() requires an AppVar name string")
    name = str(node.args[0].value).upper()
    offset = literal_integer(node.args[1], "AppVar offset")
    _emit_byte_address(compiler, name, offset)
    compiler.emit("    ld a,(hl)")
    compiler.emit("    ld l,a")
    compiler.emit("    ld h,0")
