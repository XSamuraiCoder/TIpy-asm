"""Command-line interface for the TIpy-asm compiler."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .compiler import Compiler
from .errors import CompileError
from .fasmg import ensure_ce_includes, ensure_fasmg
from .flashapp import build_flash_app


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="py2ez80",
        description="Compile Python-like source to TI-84 assembly or calculator programs.",
        epilog="This compiler builds calculator files; it does not run programs on a calculator.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    def add_source_options(command: argparse.ArgumentParser, suffix: str) -> None:
        command.add_argument("source", type=Path, help="input .py file")
        command.add_argument("-o", "--output", type=Path,
                             help=f"output {suffix} file (default: source name {suffix})")
        command.add_argument("--name", help="TI program name (up to 8 characters)")
        command.add_argument("--target", choices=("classic", "ce", "both"), default="classic",
                             help="calculator architecture to generate (default: classic)")

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
    args = parser.parse_args()

    try:
        source = args.source.read_text(encoding="utf-8")
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
            assembly = Compiler(args.name or args.source.stem, target).compile(source)
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
                include_root = ensure_ce_includes() if target == "ce" else None
                with tempfile.TemporaryDirectory(prefix="ti84py-") as temp_dir:
                    asm_path = Path(temp_dir) / (args.source.stem + ("_ce" if target == "ce" else "") + ".asm")
                    asm_path.write_text(assembly, encoding="ascii")
                    assembler_path = str(Path(assembler).resolve()) if Path(assembler).is_file() else assembler
                    command = [assembler_path, str(asm_path), str(output.resolve())]
                    result = subprocess.run(command, cwd=include_root, text=True, capture_output=True)
                    if result.returncode:
                        details = (result.stdout + result.stderr).strip()
                        raise CompileError(f"assembler failed for {target} (exit {result.returncode})" + (f":\n{details}" if details else ""))
                    if not output.is_file():
                        raise CompileError(f"assembler completed without creating {output}")
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(assembly, encoding="ascii")
            outputs.append(output)
    except (OSError, CompileError, UnicodeEncodeError) as exc:
        print(f"py2ez80: error: {exc}", file=sys.stderr)
        return 1

    for output in outputs:
        print(f"Wrote {output}")
    return 0
