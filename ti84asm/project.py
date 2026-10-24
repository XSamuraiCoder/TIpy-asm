"""Project configuration: a project's pyproject.toml plays the role of a CEdev Makefile.

Example ``[tool.tipy]`` table::

    [tool.tipy]
    name = "BOUNCE"          # calculator program name, 1-8 letters/digits
    description = "..."      # optional, free text
    main = "src/main.py"     # entry source file, relative to pyproject.toml
    target = "ce"            # classic, ce, or both
    bindir = "bin"           # output folder (like CEdev's BINDIR)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import CompileError

try:                                   # Python 3.11+
    import tomllib
except ModuleNotFoundError:            # Python 3.10: pip installs tomli for us
    import tomli as tomllib            # type: ignore[no-redef]

TARGETS = ("classic", "ce", "both")


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    name: str
    description: str
    main: Path
    target: str
    bindir: Path


def find_project_file(start: Path) -> Path:
    """Return the pyproject.toml in ``start`` (a directory) or ``start`` itself (a file)."""
    path = start / "pyproject.toml" if start.is_dir() else start
    if not path.is_file():
        raise CompileError(f"no pyproject.toml found in {start}; pass a source file or run from a project folder")
    return path


def load_project(start: Path) -> ProjectConfig:
    path = find_project_file(start)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CompileError(f"cannot read {path}: {exc}") from exc
    table = data.get("tool", {}).get("tipy")
    if table is None:
        raise CompileError(f"{path} has no [tool.tipy] section")
    unknown = set(table) - {"name", "description", "main", "target", "bindir"}
    if unknown:
        raise CompileError(f"{path}: unknown [tool.tipy] key(s): {', '.join(sorted(unknown))}")
    root = path.parent
    name = table.get("name") or data.get("project", {}).get("name", "")
    name = re.sub(r"[^A-Za-z0-9]", "", str(name))[:8]
    if not re.fullmatch(r"[A-Za-z0-9]{1,8}", name or ""):
        raise CompileError(f"{path}: [tool.tipy] name must be 1-8 ASCII letters or digits")
    target = table.get("target", "ce")
    if target not in TARGETS:
        raise CompileError(f"{path}: target must be one of {', '.join(TARGETS)}")
    main = root / table.get("main", "src/main.py")
    if not main.is_file():
        raise CompileError(f"{path}: main source file not found: {main}")
    return ProjectConfig(root=root, name=name, description=str(table.get("description", "")),
                         main=main, target=target, bindir=root / table.get("bindir", "bin"))


# --------------------------------------------------------------------------
# Multi-file sources: like CEdev compiling every file in src/, ``from name
# import ...`` pulls ``name.py`` from the same folder into the program.

@dataclass(frozen=True)
class Segment:
    start: int      # first line of this piece in the merged source (1-based)
    length: int
    path: Path


def load_sources(main: Path) -> tuple[str, list[Segment]]:
    """Return the merged program text and a line map back to the original files."""
    import ast

    folder = main.parent
    chunks: list[tuple[Path, str]] = []
    included: set[Path] = set()

    def expand(path: Path, stack: tuple[Path, ...]) -> None:
        resolved = path.resolve()
        if resolved in stack:
            chain = " -> ".join(p.name for p in (*stack, resolved))
            raise CompileError(f"circular import: {chain}")
        if resolved in included:
            return
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError) as exc:
            where = getattr(exc, "lineno", None)
            raise CompileError(f"{path.name}" + (f" line {where}" if where else "") + f": {getattr(exc, 'msg', exc)}") from exc
        lines = text.splitlines()
        local_deps: list[Path] = []
        for node in tree.body:
            target = None
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and "." not in node.module:
                candidate = folder / f"{node.module}.py"
                if candidate.is_file():
                    target = candidate
                    names = [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "." not in alias.name and (folder / f"{alias.name}.py").is_file():
                        raise CompileError(f"{path.name} line {node.lineno}: use 'from {alias.name} import NAME' "
                                           f"(plain 'import {alias.name}' is not supported for project files)")
            if target is None:
                continue
            local_deps.append(target)
            for i in range(node.lineno - 1, node.end_lineno):     # blank the import, keep line numbers
                lines[i] = ""
            _check_names(target, names, path.name, node.lineno)
        for dep in local_deps:
            expand(dep, (*stack, resolved))
        included.add(resolved)
        chunks.append((path, "\n".join(lines) + "\n"))

    expand(main, ())
    merged, segments, line = [], [], 1
    for path, text in chunks:
        count = text.count("\n")
        segments.append(Segment(line, count, path))
        merged.append(text)
        line += count
    return "".join(merged), segments


def _check_names(module: Path, names: list[str], importer: str, lineno: int) -> None:
    import ast

    if "*" in names:
        return
    defined: set[str] = set()
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined.add(node.name)
        else:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    defined.add(sub.id)
    missing = [n for n in names if n not in defined]
    if missing:
        raise CompileError(f"{importer} line {lineno}: {module.name} does not define {', '.join(missing)}")


def translate_lines(message: str, segments: list[Segment]) -> str:
    """Rewrite 'line N' in a compiler error so it points at the original file."""
    def swap(match: "re.Match[str]") -> str:
        number = int(match.group(1))
        for seg in segments:
            if seg.start <= number < seg.start + seg.length:
                return f"{seg.path.name} line {number - seg.start + 1}"
        return match.group(0)
    return re.sub(r"(?<![\w.])line (\d+)", swap, message)


def clean_project(config: "ProjectConfig") -> Path | None:
    """Delete the project's build folder (CEdev's ``make clean``); return it if removed."""
    import shutil

    bindir = config.bindir.resolve()
    root = config.root.resolve()
    if bindir == root or root not in bindir.parents:
        raise CompileError(f"refusing to delete {bindir}: bindir must be a folder inside the project")
    if not bindir.exists():
        return None
    shutil.rmtree(bindir)
    return bindir
