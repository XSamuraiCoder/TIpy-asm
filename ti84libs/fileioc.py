"""File I/O library for TIpy-asm.

Provides file operations similar to CEdev's fileioc library, for working
with AppVars, programs, and other calculator files.

Usage:
    from ti84 import fileioc
    
    # Open a file for reading
    f = fileioc.open("MYDATA", "r")
    
    # Read data
    data = fileioc.read(f, 100)
    
    # Write data
    fileioc.write(f, my_data)
    
    # Close file
    fileioc.close(f)
    
    # Get file size
    size = fileioc.size("MYDATA")
    
    # Check if file exists
    exists = fileioc.exists("MYDATA")
"""

from __future__ import annotations

import ast

from ti84asm.errors import CompileError


# File modes
MODE_READ = "r"
MODE_WRITE = "w"
MODE_APPEND = "a"
MODE_READ_WRITE = "r+"

# File types
TYPE_PROGRAM = 0x06  # Protected program
TYPE_APPVAR = 0x15   # AppVar
TYPE_LIST = 0x01     # List
TYPE_MATRIX = 0x02   # Matrix

# Public API for the assembly backend
ASSEMBLY_API = {
    "open",
    "close",
    "read",
    "write",
    "seek",
    "tell",
    "size",
    "exists",
    "delete",
    "create",
    "rename",
}


def _emit_open(compiler, node: ast.Call) -> None:
    """Open a file for reading/writing."""
    if len(node.args) not in (1, 2) or node.keywords:
        raise CompileError("open() takes filename and optional mode")
    
    name_node = node.args[0]
    if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
        raise CompileError("open() requires a string literal filename")
    
    name = name_node.value
    if not 1 <= len(name) <= 8 or not name.isalnum():
        raise CompileError("Calculator filenames are 1-8 alphanumeric characters")
    
    mode = node.args[1].value if len(node.args) == 2 and isinstance(node.args[1], ast.Constant) else MODE_READ
    
    if compiler.target == "ce":
        # CE: Use OS file operations
        compiler.emit(f"    ld hl,{name}")
        compiler.emit("    call ti.os.GetAppVarData")
        compiler.emit("    jr nc,file_not_found")
        # TODO: Return file handle
        compiler.emit("    ; File opened successfully")
    else:
        raise CompileError("fileioc.open() requires CE target")


def _emit_close(compiler, node: ast.Call) -> None:
    """Close a file."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("close() takes file handle")
    
    if compiler.target == "ce":
        compiler.emit("    ; fileioc.close() - TODO: implement")
    else:
        raise CompileError("fileioc.close() requires CE target")


def _emit_read(compiler, node: ast.Call) -> None:
    """Read data from a file."""
    if len(node.args) not in (2, 3) or node.keywords:
        raise CompileError("read() takes file handle, size, and optional buffer")
    
    if compiler.target == "ce":
        compiler.emit("    ; fileioc.read() - TODO: implement")
    else:
        raise CompileError("fileioc.read() requires CE target")


def _emit_write(compiler, node: ast.Call) -> None:
    """Write data to a file."""
    if len(node.args) != 2 or node.keywords:
        raise CompileError("write() takes file handle and data")
    
    if compiler.target == "ce":
        compiler.emit("    ; fileioc.write() - TODO: implement")
    else:
        raise CompileError("fileioc.write() requires CE target")


def _emit_seek(compiler, node: ast.Call) -> None:
    """Seek to position in file."""
    if len(node.args) not in (2, 3) or node.keywords:
        raise CompileError("seek() takes file handle, offset, and optional whence")
    
    if compiler.target == "ce":
        compiler.emit("    ; fileioc.seek() - TODO: implement")
    else:
        raise CompileError("fileioc.seek() requires CE target")


def _emit_tell(compiler, node: ast.Call) -> None:
    """Get current position in file."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("tell() takes file handle")
    
    if compiler.target == "ce":
        compiler.emit("    ; fileioc.tell() - TODO: implement")
    else:
        raise CompileError("fileioc.tell() requires CE target")


def _emit_size(compiler, node: ast.Call) -> None:
    """Get file size."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("size() takes filename")
    
    name_node = node.args[0]
    if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
        raise CompileError("size() requires a string literal filename")
    
    if compiler.target == "ce":
        name = name_node.value
        compiler.emit(f"    ld hl,{name}")
        compiler.emit("    call ti.os.GetAppVarSize")
        compiler.emit("    jr nc,file_not_found")
        # HL contains size
    else:
        raise CompileError("fileioc.size() requires CE target")


def _emit_exists(compiler, node: ast.Call) -> None:
    """Check if file exists."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("exists() takes filename")
    
    name_node = node.args[0]
    if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
        raise CompileError("exists() requires a string literal filename")
    
    if compiler.target == "ce":
        name = name_node.value
        compiler.emit(f"    ld hl,{name}")
        compiler.emit("    call ti.os.GetAppVarData")
        compiler.emit("    ld hl,1")
        compiler.emit("    ret nc")
        compiler.emit("    ld hl,0")
    else:
        raise CompileError("fileioc.exists() requires CE target")


def _emit_delete(compiler, node: ast.Call) -> None:
    """Delete a file."""
    if len(node.args) != 1 or node.keywords:
        raise CompileError("delete() takes filename")
    
    name_node = node.args[0]
    if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
        raise CompileError("delete() requires a string literal filename")
    
    if compiler.target == "ce":
        name = name_node.value
        compiler.emit(f"    ld hl,{name}")
        compiler.emit("    call ti.os.DelAppVar")
    else:
        raise CompileError("fileioc.delete() requires CE target")


def _emit_create(compiler, node: ast.Call) -> None:
    """Create a new AppVar."""
    if len(node.args) not in (1, 2) or node.keywords:
        raise CompileError("create() takes filename and optional initial data")
    
    name_node = node.args[0]
    if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
        raise CompileError("create() requires a string literal filename")
    
    if compiler.target == "ce":
        name = name_node.value
        compiler.emit(f"    ld hl,{name}")
        if len(node.args) == 2:
            # Has initial data - need to create with data
            compiler.emit("    ; create with data - TODO")
        else:
            compiler.emit("    call ti.os.CreateAppVar")
    else:
        raise CompileError("fileioc.create() requires CE target")


def _emit_rename(compiler, node: ast.Call) -> None:
    """Rename a file."""
    if len(node.args) != 2 or node.keywords:
        raise CompileError("rename() takes old name and new name")
    
    if compiler.target == "ce":
        compiler.emit("    ; fileioc.rename() - TODO: implement")
    else:
        raise CompileError("fileioc.rename() requires CE target")


def emit_call(compiler, node: ast.Call) -> None:
    """Emit a fileioc library call."""
    if not isinstance(node.func, ast.Attribute):
        raise CompileError("fileioc calls must use a fileioc library name")
    
    method = node.func.attr
    
    if method == "open":
        _emit_open(compiler, node)
    elif method == "close":
        _emit_close(compiler, node)
    elif method == "read":
        _emit_read(compiler, node)
    elif method == "write":
        _emit_write(compiler, node)
    elif method == "seek":
        _emit_seek(compiler, node)
    elif method == "tell":
        _emit_tell(compiler, node)
    elif method == "size":
        _emit_size(compiler, node)
    elif method == "exists":
        _emit_exists(compiler, node)
    elif method == "delete":
        _emit_delete(compiler, node)
    elif method == "create":
        _emit_create(compiler, node)
    elif method == "rename":
        _emit_rename(compiler, node)
    else:
        supported = ", ".join(f"fileioc.{name}()" for name in sorted(ASSEMBLY_API))
        raise CompileError(f"fileioc library supports {supported}")
