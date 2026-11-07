"""Command-line interface for the TIpy-asm compiler."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from . import convbin, convfont, convimg
from .cedev_config import get_version as cedev_version
from .cedev_config import run as cedev_config_run
from .compiler import Compiler
from .errors import CompileError
from .fasmg import (bundled_fasmg, ensure_ce_includes, ensure_classic_include_directory, ensure_fasmg,
                    find_classic_assembler)
from .image import convert_image
from .project import (ProjectConfig, Segment, build_assets, clean_project, format_diagnostic, load_project, load_sources,
                      new_project)


def _source_options(command: argparse.ArgumentParser, suffix: str) -> None:
    command.add_argument("source", type=Path, nargs="?",
                         help="input .py file, or a project folder (default: the project in or above the current folder)")
    command.add_argument("--project", type=Path, metavar="DIR",
                         help="project folder containing pyproject.toml (default: search from the current folder)")
    command.add_argument("-o", "--output", type=Path, help=f"output {suffix} file (default: source name {suffix})")
    command.add_argument("--name", help="TI program name (up to 8 characters)")
    command.add_argument("--target", choices=("classic", "ce", "both"), default=None,
                         help="calculator architecture to generate (default: project target, else classic)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tipy-asm",
        description="Compile Python-like source to TI-84 assembly or calculator programs.",
        epilog="Start with: tipy-asm new mygame, then run tipy-asm build inside it. "
               "This compiler builds calculator files; it does not run programs on a calculator.",
    )
    parser.add_argument("--version", action="version", version=f"tipy-asm {_version()}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    new_parser = commands.add_parser("new", help="create a project that builds straight away")
    new_parser.add_argument("folder", type=Path, help="folder to create; use . for the current folder")
    new_parser.add_argument("--name", help="program name, 1-8 letters or digits (default: from the folder)")
    new_parser.add_argument("--target", choices=("classic", "ce", "both"), default="ce", help="default: ce")

    build = commands.add_parser("build", help="assemble source into calculator .8xp programs and build assets")
    _source_options(build, ".8xp")
    build.add_argument("--classic-assembler", help="path to SPASM-ng (default: spasm-ng, spasm, or spasm64 on PATH)")
    build.add_argument("--ce-assembler", help="path to fasmg (default: fasmg on PATH)")
    build.add_argument("--keep-asm", action="store_true", help="also write the generated assembly next to the program")
    build.add_argument("--force", action="store_true", help="rebuild assets even if they are up to date")
    build.add_argument("--watch", action="store_true", help="rebuild whenever a source file or asset changes")

    compile_parser = commands.add_parser("compile", help="compile source to assembly without assembling it")
    _source_options(compile_parser, ".asm")

    check = commands.add_parser("check", help="report errors on every target without writing files")
    check.add_argument("source", type=Path, nargs="?", help="input .py file or project folder (default: current project)")
    check.add_argument("--project", type=Path, metavar="DIR", help="project folder containing pyproject.toml")
    check.add_argument("--target", choices=("classic", "ce", "both", "flash"), default=None,
                       help="target to check (default: project target, else both assembly targets)")

    flash = commands.add_parser("flash-app", help="link a CEdev Flash App and build its installer")
    flash.add_argument("source", type=Path, nargs="?", help="input .py file (default: the project's main file)")
    flash.add_argument("--project", type=Path, metavar="DIR", help="project folder containing pyproject.toml")
    flash.add_argument("--project-dir", type=Path,
                       help="folder to build in, which may hold a custom installer/makefile "
                            "(default: [tool.tipy.flash] project_dir, else the project folder)")
    flash.add_argument("--name", help="Flash App name (up to 8 characters)")
    flash.add_argument("--appvar-prefix", help="override the installer's payload AppVar prefix (1-6 letters/digits)")
    flash.add_argument("--installer-name", help="override the installer's calculator program name")
    flash.add_argument("--appvar-split-size", type=int, help="override the installer's payload split size in bytes")
    flash.add_argument("--optimize", choices=("speed", "size"), default=None,
                       help="favor runtime speed or smaller output (default: project setting, else speed)")

    clean = commands.add_parser("clean", help="delete the project's build output folder (bindir)")
    clean.add_argument("--project", type=Path, metavar="DIR", help="project folder containing pyproject.toml")

    doctor = commands.add_parser("doctor", help="show which tools are installed and how the project is set up")
    doctor.add_argument("--project", type=Path, metavar="DIR", help="project folder containing pyproject.toml")

    api = commands.add_parser("api", help="list library methods and the targets that support them")
    api.add_argument("library", nargs="?", help="library name, such as graphics")

    convbin.add_arguments(commands.add_parser("convbin", help="convert binary data to TI files or C/asm/ICE arrays (like CEdev's convbin)"))
    convimg.add_arguments(commands.add_parser("convimg", help="convert an image to an AppVar or C/asm/ICE pixel data (like CEdev's convimg)"))
    convfont.add_arguments(commands)
    config = commands.add_parser("cedev-config", help="get CEdev toolchain configuration (like CEdev's cedev-config)")
    config_group = config.add_mutually_exclusive_group(required=True)
    config_group.add_argument("--version", action="store_true", help="print toolchain version")
    config_group.add_argument("--prefix", action="store_true", help="print installation prefix")
    config_group.add_argument("--makefile", action="store_true", help="print core toolchain makefile path")

    from .project_convert.project_converter import add_arguments as project_converter_add_args
    project_converter_add_args(commands.add_parser("convert-project", help="convert a CEdev or ICE project to a TIpy-asm project"))

    image = commands.add_parser("convert-image", help="convert a PNG or other Pillow image to TIpy sprite source")
    image.add_argument("image", type=Path, help="input image file")
    image.add_argument("-o", "--output", type=Path, help="output Python source (default: IMAGE_sprite.py)")
    image.add_argument("--x", type=int, default=0, help="sprite left coordinate (default: 0)")
    image.add_argument("--y", type=int, default=0, help="sprite top coordinate (default: 0)")
    image.add_argument("--alpha-threshold", type=int, default=128, help="alpha values below this become transparent (default: 128)")
    image.add_argument("--fit", choices=("classic", "ce"), help="shrink to fit the selected calculator screen using nearest-neighbor scaling")
    return parser


def _version() -> str:
    try:
        return metadata.version("tipy-asm")
    except metadata.PackageNotFoundError:
        return "source checkout"


def _report(paths: list[Path], verb: str = "Wrote") -> None:
    for path in paths:
        size = f" ({path.stat().st_size} bytes)" if path.is_file() else ""
        print(f"{verb} {path}{size}")


# ------------------------------------------------------------------ builds
@dataclass
class BuildJob:
    source: Path
    name: str | None
    target: str
    output: Path | None
    project: ProjectConfig | None = None
    segments: list[Segment] = field(default_factory=list)


def _resolve_job(args: argparse.Namespace, default_target: str = "classic") -> BuildJob:
    """Combine a command's arguments with the project configuration, if one applies."""
    source, project_dir = args.source, args.project
    if source is not None and source.is_dir():
        source, project_dir = None, source      # `tipy-asm build path\to\project`
    project = None
    if source is None or project_dir is not None:
        project = load_project(project_dir or Path.cwd())
    name = getattr(args, "name", None)
    if name is not None and not re.fullmatch(r"[A-Za-z0-9]{1,8}", name):
        raise CompileError("TI program name must be 1-8 ASCII letters or digits")
    output = getattr(args, "output", None)
    target = args.target
    if project is not None:
        source = source or project.main
        name = name or project.name
        target = target or project.target
    return BuildJob(source, name, target or default_target, output, project)


def _output_path(job: BuildJob, target: str, suffix: str) -> Path:
    both = job.target == "both"
    if job.output:
        output = job.output
        return output.with_name(f"{output.stem}_{target}{output.suffix or suffix}") if both else output
    if job.project is not None:
        return job.project.bindir / (job.project.name + (f"_{target}" if both else "") + suffix)
    stem = job.source.stem
    if both and suffix == ".8xp":
        stem += f"_{target}"
    elif target == "ce":
        stem += "_ce"
    return job.source.with_name(stem + suffix)


def _find_assembler(target: str, explicit: str | None) -> str:
    if target == "ce":
        return explicit or ensure_fasmg()
    assembler = explicit or find_classic_assembler()
    if not assembler:
        raise CompileError("SPASM-ng assembler not found; put spasm-ng, spasm, or spasm64 on PATH, "
                           "set classic_assembler under [tool.tipy.toolchain], or pass --classic-assembler PATH. "
                           "Run 'tipy-asm doctor' to check your setup, or use --target ce")
    return assembler


def _assemble(job: BuildJob, target: str, assembly: str, program: str, output: Path, explicit: str | None) -> None:
    assembler = _find_assembler(target, explicit)
    output.parent.mkdir(parents=True, exist_ok=True)
    include_root = ensure_ce_includes() if target == "ce" else ensure_classic_include_directory(assembler)
    with tempfile.TemporaryDirectory(prefix="ti84py-") as temp_dir:
        asm_path = Path(temp_dir) / (job.source.stem + ("_ce" if target == "ce" else "") + ".asm")
        asm_path.write_text(assembly, encoding="ascii")
        assembler_output = output.resolve()
        if target == "classic":
            # SPASM uses the output basename as the TI program variable name;
            # keep that name alphanumeric even when the user's chosen desktop
            # filename has punctuation.
            assembler_output = Path(temp_dir) / f"{program}.8xp"
        assembler_path = str(Path(assembler).resolve()) if Path(assembler).is_file() else assembler
        command = [assembler_path]
        if target == "classic":
            command.extend(("-I", str(include_root)))
        command.extend((str(asm_path), str(assembler_output)))
        try:
            result = subprocess.run(command, cwd=include_root, text=True, capture_output=True)
        except OSError as exc:
            raise CompileError(f"could not run the {target} assembler {assembler_path}: {exc}") from exc
        if result.returncode:
            details = (result.stdout + result.stderr).strip()
            raise CompileError(f"assembler failed for {target} (exit {result.returncode})" + (f":\n{details}" if details else ""))
        if target == "classic" and assembler_output != output.resolve():
            shutil.copy2(assembler_output, output)
        if not output.is_file():
            raise CompileError(f"assembler completed without creating {output}")


def _targets(target: str) -> tuple[str, ...]:
    return ("classic", "ce") if target == "both" else (target,)


def _compile_job(job: BuildJob, target: str, source: str) -> tuple[str, str]:
    compiler = Compiler(job.name or job.source.stem, target, source_dir=job.source.parent)
    return compiler.compile(source), compiler.program


def _run_compile(args: argparse.Namespace, job: BuildJob) -> list[Path]:
    source, job.segments = load_sources(job.source)
    outputs = []
    for target in _targets(job.target):
        assembly, _ = _compile_job(job, target, source)
        output = _output_path(job, target, ".asm")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(assembly, encoding="ascii")
        outputs.append(output)
    return outputs


def _run_build(args: argparse.Namespace, job: BuildJob) -> list[Path]:
    source, job.segments = load_sources(job.source)
    project = job.project
    keep_asm = args.keep_asm or (project.keep_asm if project else False)
    outputs: list[Path] = []
    for target in _targets(job.target):
        assembly, program = _compile_job(job, target, source)
        output = _output_path(job, target, ".8xp")
        configured = None
        if project is not None:
            configured = project.ce_assembler if target == "ce" else project.classic_assembler
        explicit = (args.ce_assembler if target == "ce" else args.classic_assembler) or configured
        _assemble(job, target, assembly, program, output, explicit)
        outputs.append(output)
        if keep_asm:
            kept = output.with_suffix(".asm")
            kept.write_text(assembly, encoding="ascii")
            outputs.append(kept)
    if project is not None:
        written, _ = build_assets(project, args.force)
        outputs.extend(written)
    return outputs


def _watched_files(job: BuildJob) -> dict[Path, float]:
    paths = [segment.path for segment in job.segments] or [job.source]
    if job.project is not None:
        paths.extend(asset.source for asset in job.project.assets)
        paths.append(job.project.root / "pyproject.toml")
    return {path: path.stat().st_mtime for path in paths if path.exists()}


def _watch(args: argparse.Namespace) -> int:
    print("Watching for changes; press Ctrl+C to stop.")
    while True:
        job = _resolve_job(args)
        try:
            _report(_run_build(args, job))
        except (OSError, CompileError, UnicodeError) as exc:
            print(_format_error(exc, job.segments), file=sys.stderr)
        seen = _watched_files(job)
        try:
            while _watched_files(job) == seen:
                time.sleep(0.5)
        except KeyboardInterrupt:
            return 0


def _run_check(args: argparse.Namespace) -> int:
    job = _resolve_job(args, default_target="both")
    source, job.segments = load_sources(job.source)
    failures = 0
    name = job.name or job.source.stem
    for target in _targets(job.target):
        try:
            if target == "flash":
                from .cgen import FlashAppCompiler
                FlashAppCompiler(re.sub(r"[^A-Za-z0-9_]", "", name)[:8] or "APP").compile(source)
            else:
                Compiler(name, target, source_dir=job.source.parent).compile(source)
            print(f"{target}: ok")
        except CompileError as exc:
            failures += 1
            print(f"{target}: failed", file=sys.stderr)
            print(format_diagnostic(str(exc), job.segments), file=sys.stderr)
    return 1 if failures else 0


def _run_flash(args: argparse.Namespace) -> tuple[list[Path], list[Segment]]:
    from .flashapp import build_flash_app

    project = None
    if args.source is None or args.project is not None:
        project = load_project(args.project or Path.cwd())
    source_path = args.source or project.main
    flash = project.flash if project else None
    project_dir = args.project_dir or (flash.project_dir if flash else None)
    if project_dir is None:
        project_dir = project.root if project else source_path.parent
    app_name = args.name or (project.name if project else source_path.stem)
    if not app_name.isascii() or not re.fullmatch(r"[A-Za-z0-9_]{1,8}", app_name):
        raise CompileError("Flash App name must be 1-8 ASCII letters, digits, or underscores")
    source, segments = load_sources(source_path)
    try:
        return build_flash_app(
            source, project_dir, app_name,
            args.appvar_prefix or (flash.appvar_prefix if flash else None),
            args.installer_name or (flash.installer_name if flash else None),
            args.appvar_split_size or (flash.appvar_split_size if flash else None),
            args.optimize or (flash.optimize if flash else "speed"),
        ), segments
    except CompileError as exc:
        raise _WithSegments(str(exc), segments) from exc


class _WithSegments(CompileError):
    def __init__(self, message: str, segments: list[Segment]):
        super().__init__(message)
        self.segments = segments


# ------------------------------------------------------------ other commands
def _run_doctor(args: argparse.Namespace) -> int:
    def line(label: str, ok: bool, detail: str) -> None:
        print(f"  [{'ok' if ok else '--'}] {label}: {detail}")

    print(f"tipy-asm {_version()} on Python {sys.version.split()[0]}")
    print("Assembly targets")
    bundled = bundled_fasmg()
    fasmg = bundled or shutil.which("fasmg")
    origin = "bundled" if bundled else "on PATH"
    line("CE assembler (fasmg)", bool(fasmg),
         f"{fasmg} ({origin})" if fasmg else "no bundled build for this computer; install fasmg or pass --ce-assembler")
    spasm = find_classic_assembler()
    line("classic assembler (SPASM-ng)", bool(spasm), spasm or "not found; needed only for --target classic")
    print("Flash Apps")
    try:
        line("CEdev", True, cedev_version())
    except CompileError:
        line("CEdev", False, "not found; needed only for flash-app")
    make = shutil.which("make")
    line("make", bool(make), make or "not found; it comes with CEdev")
    print("Optional converters")
    try:
        __import__("PIL")
        line("Pillow", True, "installed")
    except ImportError:
        line("Pillow", False, "needed for images; install with: python -m pip install 'tipy-asm[images]'")
    print("Project")
    try:
        project = load_project(args.project or Path.cwd())
    except CompileError as exc:
        print(f"  {exc}")
        return 0
    print(f"  {project.name}: {project.main} -> {project.bindir} (target {project.target})")
    for asset in project.assets:
        state = "ok" if asset.source.is_file() else "--"
        print(f"  [{state}] asset {asset.name} ({asset.kind}): {asset.source}")
    if project.flash.project_dir:
        found = (project.flash.project_dir / "installer" / "makefile").is_file()
        line("Flash installer", found, str(project.flash.project_dir / "installer" / "makefile"))
    return 0


def _run_api(args: argparse.Namespace) -> int:
    from ti84libs.api import API, format_api

    if args.library is not None and args.library not in API:
        raise CompileError(f"unknown library {args.library}; available: {', '.join(API)}")
    print(format_api(args.library))
    return 0


def _format_error(exc: Exception, segments: list[Segment]) -> str:
    if isinstance(exc, CompileError):
        return format_diagnostic(str(exc), segments)
    return f"tipy-asm: error: {exc}"


def _dispatch(args: argparse.Namespace, job_holder: list[BuildJob]) -> int:
    command = args.command
    if command == "new":
        written = new_project(args.folder, args.name.upper() if args.name else None, args.target)
        _report(written, "Created")
        print(f"\nNext: cd {args.folder} and run tipy-asm build")
        return 0
    if command in ("convbin", "convimg"):
        _report({"convbin": convbin, "convimg": convimg}[command].run(args))
        return 0
    if command == "cedev-config":
        option = next(flag for flag in ("version", "prefix", "makefile") if getattr(args, flag))
        print(cedev_config_run([f"--{option}"]))
        return 0
    if command == "convert-project":
        from .project_convert import run as convert_project_run
        return convert_project_run(args)
    if command == "clean":
        removed = clean_project(load_project(args.project or Path.cwd()))
        print(f"Removed {removed}" if removed else "Nothing to clean")
        return 0
    if command == "convert-image":
        output = args.output or args.image.with_name(args.image.stem + "_sprite.py")
        convert_image(args.image, output, args.x, args.y, args.alpha_threshold, args.fit)
        _report([output])
        return 0
    if command == "doctor":
        return _run_doctor(args)
    if command == "api":
        return _run_api(args)
    if command == "check":
        return _run_check(args)
    if command == "flash-app":
        outputs, _ = _run_flash(args)
        _report(outputs)
        return 0
    if command == "build" and args.watch:
        return _watch(args)
    job = _resolve_job(args)
    job_holder.append(job)
    _report(_run_build(args, job) if command == "build" else _run_compile(args, job))
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["convfont"]:
        # convfont's options depend on their order, so it reads them itself, as CEdev's does.
        return convfont.main(arguments[1:])
    args = build_parser().parse_args(arguments)
    holder: list[BuildJob] = []
    try:
        return _dispatch(args, holder)
    except KeyboardInterrupt:
        return 130
    except (OSError, CompileError, UnicodeError, ValueError) as exc:
        segments = holder[0].segments if holder else getattr(exc, "segments", [])
        print(_format_error(exc, segments), file=sys.stderr)
        return 1
