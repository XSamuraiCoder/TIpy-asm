"""Command-line interface for the TIpy-asm compiler."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import convbin, convfont, convimg
from .cedev_config import run as cedev_config_run
from .compiler import Compiler
from .project_convert import run as convert_project_run
from .errors import CompileError
from .fasmg import ensure_ce_includes, ensure_classic_include_directory, ensure_fasmg
from .flashapp import build_flash_app
from .image import convert_image
from .project import clean_project, load_project, load_sources, translate_lines


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tipy-asm",
        description="Compile Python-like source to TI-84 assembly or calculator programs.",
        epilog="This compiler builds calculator files; it does not run programs on a calculator.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    def add_source_options(command: argparse.ArgumentParser, suffix: str) -> None:
        command.add_argument("source", type=Path, nargs="?",
                             help="input .py file, or a project folder (default: the project in the current folder)")
        command.add_argument("--project", type=Path, metavar="DIR",
                             help="project folder containing pyproject.toml (default: current folder)")
        command.add_argument("-o", "--output", type=Path,
                             help=f"output {suffix} file (default: source name {suffix})")
        command.add_argument("--name", help="TI program name (up to 8 characters)")
        command.add_argument("--target", choices=("classic", "ce", "both"), default=None,
                             help="calculator architecture to generate (default: project target, else classic)")

    compile_parser = commands.add_parser("compile", help="compile a Python source file to assembly")
    add_source_options(compile_parser, ".asm")
    build_parser = commands.add_parser("build", help="assemble source into calculator .8xp program files")
    add_source_options(build_parser, ".8xp")
    build_parser.add_argument("--classic-assembler", help="path to SPASM-ng (default: spasm-ng or spasm on PATH)")
    build_parser.add_argument("--ce-assembler", help="path to fasmg (default: fasmg on PATH)")
    flash_parser = commands.add_parser("flash-app", help="link a CEdev Flash App and build its installer")
    flash_parser.add_argument("source", type=Path, help="input Python-subset .py file")
    flash_parser.add_argument("--project-dir", required=True, type=Path,
                              help="copied project directory containing installer/makefile")
    flash_parser.add_argument("--name", help="Flash App name (up to 8 characters)")
    flash_parser.add_argument("--appvar-prefix",
                              help="override the copied installer's payload AppVar prefix (1-6 letters/digits)")
    flash_parser.add_argument("--installer-name",
                              help="override the copied installer's calculator program name (default: use its makefile)")
    flash_parser.add_argument("--appvar-split-size", type=int,
                              help="override the installer's payload split size in bytes (default: use its makefile)")
    flash_parser.add_argument("--optimize", choices=("speed", "size"), default="speed",
                              help="favor runtime speed or smaller output (default: speed)")
    convbin.add_arguments(commands.add_parser("convbin", help="convert binary data to TI files or C/asm/ICE arrays (like CEdev's convbin)"))
    convimg.add_arguments(commands.add_parser("convimg", help="convert an image to an AppVar or C/asm/ICE pixel data (like CEdev's convimg)"))
    convfont.add_arguments(commands.add_parser("convfont", help="convert a TTF/OTF font (or .fnt) to an AppVar or C/asm/ICE arrays using cefont"))
    cedev_config_parser = commands.add_parser("cedev-config", help="get CEdev toolchain configuration (like CEdev's cedev-config)")
    cedev_config_group = cedev_config_parser.add_mutually_exclusive_group(required=True)
    cedev_config_group.add_argument("--version", action="store_true", help="print toolchain version")
    cedev_config_group.add_argument("--prefix", action="store_true", help="print installation prefix")
    cedev_config_group.add_argument("--makefile", action="store_true", help="print core toolchain makefile path")
    
    # Project conversion command
    from .project_convert.project_converter import add_arguments as project_converter_add_args
    project_parser = commands.add_parser("convert-project", help="convert a CEdev or ICE project to TIpy-asm Python")
    project_converter_add_args(project_parser)
    
    clean_parser = commands.add_parser("clean", help="delete the project's build output folder (bindir)")
    clean_parser.add_argument("--project", type=Path, metavar="DIR",
                              help="project folder containing pyproject.toml (default: current folder)")
    image_parser = commands.add_parser("convert-image", help="convert a PNG or other Pillow image to TIpy sprite source")
    image_parser.add_argument("image", type=Path, help="input image file")
    image_parser.add_argument("-o", "--output", type=Path, help="output Python source (default: IMAGE_sprite.py)")
    image_parser.add_argument("--x", type=int, default=0, help="sprite left coordinate (default: 0)")
    image_parser.add_argument("--y", type=int, default=0, help="sprite top coordinate (default: 0)")
    image_parser.add_argument("--alpha-threshold", type=int, default=128,
                              help="alpha values below this become transparent (default: 128)")
    image_parser.add_argument("--fit", choices=("classic", "ce"),
                              help="shrink to fit the selected calculator screen using nearest-neighbor scaling")
    args = parser.parse_args()

    segments = []
    try:
        if args.command == "convbin":
            for written in convbin.run(args):
                print(f"Wrote {written}")
            return 0
        if args.command == "convimg":
            for written in convimg.run(args):
                print(f"Wrote {written}")
            return 0
        if args.command == "convfont":
            for written in convfont.run(args):
                print(f"Wrote {written}")
            return 0
        if args.command == "cedev-config":
            option_map = {
                "version": "--version",
                "prefix": "--prefix",
                "makefile": "--makefile"
            }
            # Find which option was set
            option = None
            for key, value in vars(args).items():
                if key in option_map and value:
                    option = option_map[key]
                    break
            if option:
                print(cedev_config_run([option]))
            return 0
        if args.command == "convert-project":
            for written in convert_project_run(args):
                print(f"Converted: {written}")
            print(f"\nProject converted to: {args.output or (args.project.parent / f'{args.project.name}_converted')}")
            return 0
        if args.command == "clean":
            removed = clean_project(load_project(args.project or Path.cwd()))
            print(f"Removed {removed}" if removed else "Nothing to clean")
            return 0
        if (args.command in ("compile", "build") and args.name is not None
                and not re.fullmatch(r"[A-Za-z0-9]{1,8}", args.name)):
            raise CompileError("TI program name must be 1-8 ASCII letters or digits")
        if args.command == "convert-image":
            output = args.output or args.image.with_name(args.image.stem + "_sprite.py")
            convert_image(args.image, output, args.x, args.y, args.alpha_threshold, args.fit)
            print(f"Wrote {output}")
            return 0
        if args.command in ("compile", "build"):
            if args.source is not None and args.source.is_dir():
                args.project, args.source = args.source, None      # `tipy-asm build path\to\project`
            if args.source is None or args.project is not None:
                project = load_project(args.project or Path.cwd())
                if args.source is None:
                    args.source = project.main
                args.name = args.name or project.name
                args.target = args.target or project.target
                if args.output is None:
                    args.output = project.bindir / (project.name + (".8xp" if args.command == "build" else ".asm"))
            args.target = args.target or "classic"
        source, segments = load_sources(args.source)
        if args.command == "flash-app":
            app_name = args.name or args.source.stem
            if not app_name.isascii() or not re.fullmatch(r"[A-Za-z0-9_]{1,8}", app_name):
                raise CompileError("Flash App name must be 1-8 ASCII letters, digits, or underscores")
            outputs = build_flash_app(source, args.project_dir, app_name, args.appvar_prefix,
                                      args.installer_name, args.appvar_split_size, args.optimize)
            for output in outputs:
                print(f"Wrote {output}")
            return 0
        targets = ("classic", "ce") if args.target == "both" else (args.target,)
        outputs: list[Path] = []
        for target in targets:
            building = args.command == "build"
            if args.output:
                output = args.output
                if args.target == "both":
                    output = output.with_name(f"{output.stem}_{target}{output.suffix or ('.8xp' if building else '.asm')}")
            else:
                stem = args.source.stem + ("_ce" if target == "ce" else "")
                if args.target == "both" and building:
                    stem = args.source.stem + "_" + target
                output = args.source.with_name(stem + (".8xp" if building else ".asm"))
            compiler = Compiler(args.name or args.source.stem, target)
            assembly = compiler.compile(source)
            if building:
                assembler = (args.ce_assembler if target == "ce" else args.classic_assembler)
                assembler = assembler or shutil.which("fasmg" if target == "ce" else "spasm-ng")
                if target == "ce" and not assembler:
                    assembler = ensure_fasmg()
                if target == "classic" and not assembler:
                    assembler = shutil.which("spasm")
                if not assembler:
                    tool = "fasmg" if target == "ce" else "SPASM-ng (or spasm)"
                    raise CompileError(f"{tool} assembler not found; install it or pass --{'ce' if target == 'ce' else 'classic'}-assembler PATH")
                output.parent.mkdir(parents=True, exist_ok=True)
                include_root = (ensure_ce_includes() if target == "ce"
                                else ensure_classic_include_directory(assembler))
                with tempfile.TemporaryDirectory(prefix="ti84py-") as temp_dir:
                    asm_path = Path(temp_dir) / (args.source.stem + ("_ce" if target == "ce" else "") + ".asm")
                    asm_path.write_text(assembly, encoding="ascii")
                    assembler_output = output.resolve()
                    if target == "classic":
                        # SPASM uses the output basename as the TI program
                        # variable name; keep that name alphanumeric even when
                        # the user's chosen desktop filename has punctuation.
                        assembler_output = Path(temp_dir) / f"{compiler.program}.8xp"
                    assembler_path = str(Path(assembler).resolve()) if Path(assembler).is_file() else assembler
                    command = [assembler_path]
                    if target == "classic":
                        command.extend(("-I", str(include_root)))
                    command.extend((str(asm_path), str(assembler_output)))
                    result = subprocess.run(command, cwd=include_root, text=True, capture_output=True)
                    if result.returncode:
                        details = (result.stdout + result.stderr).strip()
                        raise CompileError(f"assembler failed for {target} (exit {result.returncode})" + (f":\n{details}" if details else ""))
                    if target == "classic" and assembler_output != output.resolve():
                        shutil.copy2(assembler_output, output)
                    if not output.is_file():
                        raise CompileError(f"assembler completed without creating {output}")
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(assembly, encoding="ascii")
            outputs.append(output)
    except (OSError, CompileError, UnicodeError) as exc:
        message = translate_lines(str(exc), segments) if isinstance(exc, CompileError) else str(exc)
        print(f"tipy-asm: error: {message}", file=sys.stderr)
        return 1

    for output in outputs:
        print(f"Wrote {output}")
    return 0