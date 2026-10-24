"""Pure-Python ``convbin``: turn binary data into TI files or source arrays.

Mirrors CEdev's ``convbin`` options and output layout so scripts written for
CEdev carry over. Supported input formats: ``bin``, ``csv``. Supported output
formats: ``bin``, ``8xp``, ``8xv``, ``8xv-split``, ``c``, ``asm``, ``ice``.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import CompileError

INPUT_FORMATS = ("bin", "csv")
OUTPUT_FORMATS = ("bin", "8xp", "8xv", "8xv-split", "c", "asm", "ice")
UNSUPPORTED = ("elf", "8ek", "8x", "8xp-compressed", "8xg", "8xg-auto-extract", "b83", "b84", "zip")
TYPE_PROGRAM, TYPE_APPVAR = 0x06, 0x15          # protected program, AppVar
MIN_SPLIT_SIZE = 4096                            # smaller maximums are rejected by CEdev's convbin
DEFAULT_SPLIT_SIZE = 65200
MAX_VAR_SIZE = 65500


@dataclass
class ConvbinJob:
    inputs: list[tuple[Path, str]] = field(default_factory=list)   # (file, input format)
    output: Path | None = None
    oformat: str = "bin"
    name: str | None = None
    archive: bool = False
    uppercase: bool = False
    append: bool = False
    max_var_size: int = DEFAULT_SPLIT_SIZE
    comment: str = ""


def read_input(path: Path, fmt: str) -> bytes:
    if fmt in UNSUPPORTED:
        raise CompileError(f"input format '{fmt}' is not supported by the Python convbin yet")
    if fmt not in INPUT_FORMATS:
        raise CompileError(f"unknown input format '{fmt}'")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CompileError(f"cannot read {path}: {exc}") from exc
    if fmt == "bin":
        return raw
    values = []
    for token in re.split(r"[,\s]+", raw.decode("utf-8", errors="strict").strip()):
        if not token:
            continue
        try:
            value = int(token, 0)
        except ValueError as exc:
            raise CompileError(f"{path}: '{token}' is not a number") from exc
        if not 0 <= value <= 255:
            raise CompileError(f"{path}: {value} does not fit in a byte")
        values.append(value)
    return bytes(values)


def ti_file(var_type: int, name: str, data: bytes, archived: bool = False, comment: str = "") -> bytes:
    """Build a TI-83 Premium CE / TI-84 Plus CE variable file (.8xp, .8xv, ...)."""
    encoded = name.encode("ascii")
    if not 1 <= len(encoded) <= 8:
        raise CompileError("on-calc names are 1-8 characters")
    if len(data) > MAX_VAR_SIZE:
        raise CompileError(f"{len(data)} bytes is too large for one variable (max {MAX_VAR_SIZE}); use 8xv-split")
    body = len(data).to_bytes(2, "little") + data
    entry = (b"\x0d\x00" + len(body).to_bytes(2, "little") + bytes([var_type]) + encoded.ljust(8, b"\0")
             + b"\x00" + (b"\x80" if archived else b"\x00") + len(body).to_bytes(2, "little") + body)
    header = b"**TI83F*\x1a\x0a\x00" + comment.encode("ascii", "replace")[:42].ljust(42, b"\0")
    return header + len(entry).to_bytes(2, "little") + entry + (sum(entry) & 0xFFFF).to_bytes(2, "little")


def _rows(data: bytes, per_row: int = 32):
    for start in range(0, len(data), per_row):
        yield data[start:start + per_row]


def to_c(name: str, data: bytes) -> str:
    rows = list(_rows(data))
    lines = [",".join(f"0x{b:02x}" for b in row) for row in rows]
    body = ",\n    ".join(lines)
    return f"unsigned char {name}[{len(data)}] =\n{{\n    {body}\n}};\n"


def to_asm(name: str, data: bytes) -> str:
    lines = "".join("\tdb\t" + ",".join(f"${b:02x}" for b in row) + "\n" for row in _rows(data))
    return f"{name}:\n; {len(data)} bytes\n{lines}"


def to_ice(name: str, data: bytes) -> str:
    return f'{name} | {len(data)} bytes\n"{data.hex().upper()}"\n'


def convert(job: ConvbinJob) -> list[Path]:
    """Run a conversion job; return the files written."""
    if not job.inputs:
        raise CompileError("convbin needs at least one input file (-i)")
    if job.output is None:
        raise CompileError("convbin needs an output file (-o)")
    if job.oformat in UNSUPPORTED:
        raise CompileError(f"output format '{job.oformat}' is not supported by the Python convbin yet")
    if job.oformat not in OUTPUT_FORMATS:
        raise CompileError(f"unknown output format '{job.oformat}'")
    data = b"".join(read_input(path, fmt) for path, fmt in job.inputs)
    name = job.name or job.output.stem
    if job.oformat in ("8xp", "8xv", "8xv-split") or job.uppercase:
        if job.uppercase:
            name = name.upper()
        if not re.fullmatch(r"[A-Za-z0-9]{1,8}", name):
            raise CompileError("on-calc names are 1-8 letters or digits")
    job.output.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def write(path: Path, payload: bytes) -> None:
        mode = "ab" if job.append else "wb"
        path.write_bytes(payload) if mode == "wb" else path.open(mode).write(payload)
        written.append(path)

    if job.oformat == "bin":
        write(job.output, data)
    elif job.oformat == "8xp":
        write(job.output, ti_file(TYPE_PROGRAM, name, data, job.archive, job.comment))
    elif job.oformat == "8xv":
        write(job.output, ti_file(TYPE_APPVAR, name, data, job.archive, job.comment))
    elif job.oformat == "8xv-split":
        size = job.max_var_size
        if size < MIN_SPLIT_SIZE:
            raise CompileError("Maximum variable size too small.")
        if size > MAX_VAR_SIZE:
            raise CompileError(f"maximum variable size is {MAX_VAR_SIZE}")
        chunks = [data[i:i + size] for i in range(0, len(data), size)] or [b""]
        if len(name) > 7 and len(chunks) > 9 or len(name) + len(str(len(chunks) - 1)) > 8:
            raise CompileError("name too long to number the split AppVars (max 8 characters including the index)")
        for index, chunk in enumerate(chunks):
            target = job.output.with_name(f"{job.output.stem}.{index}{job.output.suffix}")
            # Split AppVars are archived so they survive RAM clears, as in CEdev.
            write(target, ti_file(TYPE_APPVAR, f"{name}{index}", chunk, True, job.comment))
    elif job.oformat in ("c", "asm", "ice"):
        text = {"c": to_c, "asm": to_asm, "ice": to_ice}[job.oformat](name, data)
        write(job.output, text.encode("ascii"))
    return written


# ---------------------------------------------------------------- command line
class _Format(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.pending_format = values


class _Input(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        items = list(getattr(namespace, "inputs", None) or [])
        items.append((Path(values), getattr(namespace, "pending_format", "bin")))
        namespace.inputs = items
        namespace.pending_format = "bin"      # -j applies to the next -i only, as in CEdev


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add CEdev-style convbin options (a subset; see the module docstring)."""
    parser.set_defaults(pending_format="bin", inputs=[])
    parser.add_argument("-i", "--input", action=_Input, metavar="FILE", help="input file; repeat to append in order")
    parser.add_argument("-j", "--iformat", action=_Format, metavar="MODE",
                        help="format of the next input file: " + ", ".join(INPUT_FORMATS) + " (default bin)")
    parser.add_argument("-o", "--output", type=Path, metavar="FILE", help="output file")
    parser.add_argument("-k", "--oformat", default="bin", metavar="MODE",
                        help="output format: " + ", ".join(OUTPUT_FORMATS) + " (default bin)")
    parser.add_argument("-n", "--name", help="on-calc name, or array/label name for c, asm, ice")
    parser.add_argument("-r", "--archive", action="store_true", help="mark TI variables as archived")
    parser.add_argument("-u", "--uppercase", action="store_true", help="uppercase the on-calc name")
    parser.add_argument("-a", "--append", action="store_true", help="append to the output file")
    parser.add_argument("-m", "--maxvarsize", type=int, default=DEFAULT_SPLIT_SIZE,
                        help=f"maximum size of each split AppVar (default {DEFAULT_SPLIT_SIZE})")
    parser.add_argument("-b", "--comment", default="", help="comment stored in TI files")
    for flag, what in (("-c", "compression"), ("-p", "input compression"), ("-e", "8xp compression")):
        parser.add_argument(flag, metavar="MODE", help=f"{what} (not supported yet)")


def run(args: argparse.Namespace) -> list[Path]:
    for flag, value in (("-c", args.c), ("-p", args.p), ("-e", args.e)):
        if value:
            raise CompileError(f"convbin {flag} (compression) is not supported yet")
    if args.output is None:
        raise CompileError("convbin needs an output file (-o)")
    return convert(ConvbinJob(inputs=list(args.inputs), output=args.output, oformat=args.oformat, name=args.name,
                              archive=args.archive, uppercase=args.uppercase, append=args.append,
                              max_var_size=args.maxvarsize, comment=args.comment))


def run_with_args() -> int:
    import sys
    parser = argparse.ArgumentParser(
        prog="convbin",
        description="Convert binary data to TI files or C/asm/ICE arrays (CEdev's convbin)",
    )
    add_arguments(parser)
    try:
        args = parser.parse_args()
        for written in run(args):
            print(f"Wrote {written}")
        return 0
    except Exception as exc:
        print(f"convbin: error: {exc}", file=sys.stderr)
        return 1
