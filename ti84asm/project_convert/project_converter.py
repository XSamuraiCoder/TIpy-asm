"""Convert a whole CEdev or ICE project into a TIpy-asm project.

The output is a normal project: ``src/*.py``, assets declared in pyproject.toml,
and CONVERSION_NOTES.md listing anything that needs a person's attention. The
converter then compiles its own output, so it reports whether the result builds.

Usage::

    tipy-asm convert-project path/to/project -o output_folder
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..errors import CompileError
from .c_like import Conversion
from .cedev_convert import convert_cedev
from .ice_convert import convert_ice

_SKIPPED_FOLDERS = {"bin", "obj", ".git", "__pycache__"}
_IMAGE_SUFFIXES = (".png", ".bmp", ".jpg", ".jpeg", ".gif")
_ASSET_SUFFIXES = (*_IMAGE_SUFFIXES, ".ttf", ".otf", ".fnt", ".bin")
_NOTES = "CONVERSION_NOTES.md"


def detect_type(project: Path) -> str:
    """Tell CEdev and ICE projects apart by the source files they contain."""
    if project.is_file():
        return "ice" if project.suffix.lower() == ".ice" else "cedev"
    return "ice" if any(_project_files(project, (".ice",))) else "cedev"


def _project_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found = [path for path in root.rglob("*")
             if path.is_file() and path.suffix.lower() in suffixes
             and not _SKIPPED_FOLDERS.intersection(path.relative_to(root).parts[:-1])]
    return sorted(found)


def _program_name(project: Path) -> str:
    """Use the makefile's NAME when there is one, otherwise the folder's name."""
    root = project if project.is_dir() else project.parent
    for candidate in ("makefile", "Makefile"):
        makefile = root / candidate
        if makefile.is_file():
            match = re.search(r"(?m)^\s*NAME\s*[:?]?=\s*(\S+)", makefile.read_text(encoding="utf-8", errors="replace"))
            if match:
                name = re.sub(r"[^A-Za-z0-9]", "", match.group(1))[:8].upper()
                if name:
                    return name
    stem = project.stem if project.is_file() else project.name
    return re.sub(r"[^A-Za-z0-9]", "", stem)[:8].upper() or "PROGRAM"


def _python_text(conversion: Conversion, imports: list[str], defines: list[tuple[str, str]], entry: bool) -> str:
    lines = [f"from {module} import *" for module in imports]
    head = conversion.code
    from_ti84 = ""
    if head.startswith("from ti84 import"):
        from_ti84, head = head.split("\n", 1)
        head = head.lstrip("\n")
    parts = [line for line in (from_ti84, *lines) if line]
    text = "\n".join(parts) + ("\n\n" if parts else "")
    if defines:
        text += "\n".join(f"{name} = {_define_value(value)}" for name, value in defines) + "\n\n"
    text += head
    if entry:
        text += "\n\nmain()\n"
    return text


def _define_value(value: str) -> str:
    cleaned = value.split("//")[0].split("/*")[0].strip()
    return re.sub(r"(?<=\d)[uUlL]+\b", "", cleaned) or "0"


class ProjectConverter:
    """Converts an entire CEdev or ICE project to a TIpy-asm project."""

    def __init__(self, project_path: Path, output_path: Path, project_type: str = "auto"):
        self.project_path = Path(project_path)
        self.output_path = Path(output_path)
        if not self.project_path.exists():
            raise CompileError(f"project not found: {project_path}")
        self.project_type = detect_type(self.project_path) if project_type == "auto" else project_type
        self.converted_files: list[Path] = []
        self.warnings: list[str] = []
        self.root = self.project_path if self.project_path.is_dir() else self.project_path.parent

    def convert(self) -> list[Path]:
        if self.output_path.resolve() == self.root.resolve():
            raise CompileError("choose an output folder other than the project being converted")
        sources = self._sources()
        if not sources:
            kind = ".ice" if self.project_type == "ice" else ".c"
            raise CompileError(f"no {kind} source files found in {self.project_path}")
        self.output_path.mkdir(parents=True, exist_ok=True)
        modules = self._translate_all(sources)
        main_module = next((name for name, item in modules.items() if item["conversion"].uses_main), None)
        if main_module is None:
            main_module = next(iter(modules))
            self.warnings.append(f"no main() function found; using {main_module}.py as the program entry")
        for name, item in modules.items():
            self._write_module(name, item, modules, name == main_module)
        assets = self._copy_assets()
        self._write_pyproject(main_module, assets)
        self._write_notes()
        return self.converted_files

    def _sources(self) -> list[Path]:
        suffix = (".ice",) if self.project_type == "ice" else (".c",)
        if self.project_path.is_file():
            return [self.project_path]
        return _project_files(self.project_path, suffix)

    def _translate_all(self, sources: list[Path]) -> dict[str, dict]:
        translate = convert_ice if self.project_type == "ice" else convert_cedev
        modules: dict[str, dict] = {}
        for source in sources:
            name = re.sub(r"\W", "_", source.stem)
            if name in modules:
                raise CompileError(f"two source files convert to {name}.py; rename one of them")
            conversion = translate(source)
            self.warnings.extend(f"{source.relative_to(self.root)}: {warning}" for warning in conversion.warnings)
            modules[name] = {"source": source, "conversion": conversion}
        if self.project_type != "ice":
            for header in _project_files(self.root, (".h",)):
                name = re.sub(r"\W", "_", header.stem)
                conversion = translate(header)
                self.warnings.extend(f"{header.relative_to(self.root)}: {warning}" for warning in conversion.warnings)
                if name in modules:
                    # A header's constants are placed at the top of its .c file's module.
                    modules[name]["conversion"].defines[:0] = conversion.defines
                    modules[name]["conversion"].includes.extend(conversion.includes)
                elif conversion.defines:
                    modules[name] = {"source": header, "conversion": conversion}
        return modules

    def _write_module(self, name: str, item: dict, modules: dict[str, dict], entry: bool) -> None:
        conversion: Conversion = item["conversion"]
        imports = []
        for include in conversion.includes:
            module = re.sub(r"\W", "_", Path(include).stem)
            if module in modules and module != name and module not in imports:
                imports.append(module)
        output = self.output_path / "src" / f"{name}.py"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_python_text(conversion, imports, conversion.defines, entry and conversion.uses_main), encoding="utf-8")
        self.converted_files.append(output)

    def _copy_assets(self) -> list[str]:
        declared = []
        if self.project_path.is_file():
            return declared
        for asset in _project_files(self.project_path, _ASSET_SUFFIXES):
            output = self.output_path / "assets" / asset.name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, output)
            self.converted_files.append(output)
            name = re.sub(r"[^A-Za-z0-9]", "", asset.stem)[:8].upper()
            if re.fullmatch(r"[A-Z][A-Z0-9]*", name) and name not in {entry.split('"')[3] for entry in declared}:
                kind = ("sprite" if asset.suffix.lower() in _IMAGE_SUFFIXES
                        else "font" if asset.suffix.lower() in (".fnt", ".ttf", ".otf") else "binary")
                size = "\nsize = 16" if asset.suffix.lower() in (".ttf", ".otf") else ""
                declared.append(f'[[tool.tipy.assets]]\nsource = "assets/{asset.name}"\nname = "{name}"\nkind = "{kind}"{size}\n')
            else:
                self.warnings.append(f"{asset.name}: copied, but its name cannot be an AppVar name; declare it by hand")
        return declared

    def _write_pyproject(self, main_module: str, assets: list[str]) -> None:
        output = self.output_path / "pyproject.toml"
        text = (f'[tool.tipy]\nname = "{_program_name(self.project_path)}"\n'
                f'description = "Converted from {self.project_path.name}"\n'
                f'main = "src/{main_module}.py"\ntarget = "ce"\nbindir = "bin"\n')
        if assets:
            text += "\n" + "\n".join(assets)
        output.write_text(text, encoding="utf-8")
        self.converted_files.append(output)

    def _write_notes(self) -> None:
        output = self.output_path / _NOTES
        lines = [f"# Conversion notes for {self.project_path.name}", ""]
        if self.warnings:
            lines += ["Search the source for `TODO(convert)` to find what was left unconverted.", ""]
            lines += [f"- {warning}" for warning in self.warnings]
        else:
            lines.append("Everything converted without warnings.")
        lines += ["", "CEdev palette indices are not RGB565 colors, so check that colors from `gfx_SetColor()` look right."]
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.converted_files.append(output)


def convert_cedev_project(project_path: str | Path, output_path: str | Path) -> list[Path]:
    """Convert a CEdev project; return the files written."""
    return ProjectConverter(Path(project_path), Path(output_path), "cedev").convert()


def convert_ice_project(project_path: str | Path, output_path: str | Path) -> list[Path]:
    """Convert an ICE project folder or file; return the files written."""
    return ProjectConverter(Path(project_path), Path(output_path), "ice").convert()


def add_arguments(parser) -> None:
    """Add command-line arguments for convert-project."""
    parser.add_argument("project", type=Path, help="CEdev or ICE project folder, or a single source file")
    parser.add_argument("-o", "--output", type=Path, help="output folder (default: PROJECT_converted)")
    parser.add_argument("--type", choices=["auto", "cedev", "ice"], default="auto",
                        help="project type (default: detect from the source files)")
    parser.add_argument("--verbose", "-v", action="store_true", help="list every file written and every warning")


def run(args) -> int:
    """Run the conversion, then compile the result so the outcome is known."""
    from ..compiler import Compiler
    from ..project import format_diagnostic, load_project, load_sources

    project = args.project
    stem = project.stem if project.is_file() else project.name
    output = args.output or project.parent / f"{stem}_converted"
    converter = ProjectConverter(project, output, args.type)
    files = converter.convert()
    print(f"Converted {project} ({converter.project_type}) to {output}: {len(files)} file(s)")
    if args.verbose:
        for path in files:
            print(f"  {path.relative_to(output)}")
    warnings = converter.warnings
    if warnings:
        print(f"{len(warnings)} item(s) need attention; see {output / _NOTES}")
        for warning in warnings if args.verbose else warnings[:5]:
            print(f"  {warning}")
        if not args.verbose and len(warnings) > 5:
            print(f"  ...and {len(warnings) - 5} more")
    config = load_project(output)
    segments = []
    try:
        source, segments = load_sources(config.main)
        Compiler(config.name, "ce").compile(source)
    except CompileError as exc:
        print("The converted project does not compile yet:")
        print(format_diagnostic(str(exc), segments))
        print(f"Fix that, then run: tipy-asm build {output}")
        return 1
    print(f"The converted project compiles. Build it with: tipy-asm build {output}")
    return 0
