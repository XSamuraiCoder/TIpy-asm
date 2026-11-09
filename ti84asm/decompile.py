"""Decompile TI calculator files: programs back to readable source.

``tipy-asm decompile FILE`` reads a .8xp, .8xv, or other TI variable file and,
for each variable in it, writes:

- a TI-BASIC or Axe source program as text, token by token;
- an assembly program as a disassembly: Z80 for the TI-83 Plus/84 Plus
  (programs starting BBh 6Dh), eZ80 in ADL mode for the CE (EFh 7Bh), with labels
  at jump and call targets and OS routines named from the bundled include files;
- anything else, such as an AppVar, as a hex dump.

A disassembly cannot tell code from data, so tables and strings inside a
program come out as instructions too; the bytes beside each line show what is
really there.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from .errors import CompileError
from .tokens import detokenize

PROGRAM_TYPES = {5: "program", 6: "protected program"}
TYPE_NAMES = {0x00: "real", 0x01: "list", 0x02: "matrix", 0x03: "equation", 0x04: "string", 0x05: "program",
              0x06: "protected program", 0x07: "picture", 0x08: "GDB", 0x0C: "complex", 0x0D: "complex list",
              0x14: "application", 0x15: "AppVar", 0x17: "group"}
CLASSIC_ORIGIN = 0x9D95          # userMem on the TI-83 Plus and 84 Plus
CE_ORIGIN = 0xD1A881             # userMem on the CE


# ------------------------------------------------------------------ TI files

def read_variables(path: Path) -> list[dict]:
    """The variables in a TI file: name, type, and data."""
    raw = path.read_bytes()
    if raw[:8] not in (b"**TI83F*", b"**TI73**", b"**TI82**", b"**TI83**"):
        raise CompileError(f"{path} is not a TI variable file")
    end = 55 + (raw[53] | raw[54] << 8)
    at, found = 55, []
    while at + 4 <= min(end, len(raw)):
        header = raw[at] | raw[at + 1] << 8
        length = raw[at + 2] | raw[at + 3] << 8
        kind = raw[at + 4]
        name = raw[at + 5:at + 13].rstrip(b"\0")
        data_at = at + 2 + header + 2
        data = raw[data_at:data_at + length]
        found.append({"name": name.decode("latin-1"), "type": kind, "data": data})
        at = data_at + length
    return found


def _program_body(data: bytes) -> bytes:
    size = data[0] | data[1] << 8 if len(data) >= 2 else 0
    return data[2:2 + size]


# ------------------------------------------------------------------ symbols

_SYMBOLS: dict[str, dict[int, str]] = {}


def _ce_symbols() -> dict[int, str]:
    if "ce" not in _SYMBOLS:
        names: dict[int, str] = {}
        include = Path(__file__).parent / "toolchain" / "include" / "ti84pceg.inc"
        text = include.read_text(encoding="utf-8", errors="replace") if include.is_file() else ""
        for name, value in re.findall(r"^\?([\w.]+)\s*:=\s*0?([0-9A-Fa-f]+)h\b", text, re.M):
            address = int(value, 16)
            if address >= 0x400 and address < 0x100000 or address >= 0xD00000:
                names.setdefault(address, f"ti.{name}")
        _SYMBOLS["ce"] = names
    return _SYMBOLS["ce"]


def _classic_symbols() -> dict[int, str]:
    if "classic" not in _SYMBOLS:
        names: dict[int, str] = {}
        try:
            from .fasmg import ensure_classic_include_directory

            text = (ensure_classic_include_directory() / "ti83plus.inc").read_text(encoding="utf-8", errors="replace")
        except (OSError, CompileError):
            text = ""
        for name, value in re.findall(r"^(_\w+)\s+EQU\s+([0-9A-Fa-f]+)h", text, re.M | re.I):
            names.setdefault(int(value, 16), name)
        _SYMBOLS["classic"] = names
    return _SYMBOLS["classic"]


# ------------------------------------------------------------------ Z80 / eZ80

_R = ["b", "c", "d", "e", "h", "l", "(hl)", "a"]
_RP = ["bc", "de", "hl", "sp"]
_RP2 = ["bc", "de", "hl", "af"]
_CC = ["nz", "z", "nc", "c", "po", "pe", "p", "m"]
_ALU = ["add a,", "adc a,", "sub ", "sbc a,", "and ", "xor ", "or ", "cp "]
_ROT = ["rlc", "rrc", "rl", "rr", "sla", "sra", "sll", "srl"]
_IM = ["0", "0", "1", "2", "0", "0", "1", "2"]
_BLOCK = {(4, 0): "ldi", (4, 1): "cpi", (4, 2): "ini", (4, 3): "outi", (5, 0): "ldd", (5, 1): "cpd",
          (5, 2): "ind", (5, 3): "outd", (6, 0): "ldir", (6, 1): "cpir", (6, 2): "inir", (6, 3): "otir",
          (7, 0): "lddr", (7, 1): "cpdr", (7, 2): "indr", (7, 3): "otdr"}


class _Decoder:
    def __init__(self, code: bytes, origin: int, adl: bool):
        self.code, self.origin, self.adl = code, origin, adl
        self.word = 3 if adl else 2
        self.targets: set[int] = set()

    def byte(self) -> int:
        value = self.code[self.at] if self.at < len(self.code) else 0
        self.at += 1
        return value

    def imm(self) -> int:
        value = 0
        for shift in range(self.word):
            value |= self.byte() << (8 * shift)
        return value

    def disp(self) -> int:
        value = self.byte()
        return value - 256 if value >= 128 else value

    def addr(self, value: int) -> str:
        return f"${value:0{2 * self.word}X}"

    def target(self, value: int) -> str:
        self.targets.add(value)
        return f"@{value}"

    def decode(self, at: int) -> tuple[int, str]:
        """(length, text) of the instruction at offset ``at``."""
        self.at = at
        text = self._one(None)
        return self.at - at, text

    def _index(self, prefix: int | None, name: str, d: int | None = None) -> str:
        if prefix is None:
            return name
        reg = "ix" if prefix == 0xDD else "iy"
        if name == "hl":
            return reg
        if name == "h":
            return reg + "h"
        if name == "l":
            return reg + "l"
        if name == "(hl)":
            return f"({reg}{d:+d})" if d else f"({reg})"
        return name

    def _one(self, prefix: int | None) -> str:
        op = self.byte()
        if op in (0xDD, 0xFD) and prefix is None:
            return self._one(op)
        if op == 0xCB:
            return self._cb(prefix)
        if op == 0xED:
            return self._ed()
        x, y, z, p, q = op >> 6, (op >> 3) & 7, op & 7, (op >> 4) & 3, (op >> 3) & 1

        def reg(i: int) -> str:
            if prefix is not None and i == 6:
                return self._index(prefix, "(hl)", self.disp())
            return self._index(prefix, _R[i])
        if x == 1:
            if op == 0x76:
                return "halt"
            if prefix is not None and (y == 6 or z == 6):
                # ld r,(ix+d) / ld (ix+d),r keep plain h and l.
                d = self.disp()
                return f"ld {self._index(prefix, '(hl)', d) if y == 6 else _R[y]}," \
                       f"{self._index(prefix, '(hl)', d) if z == 6 else _R[z]}"
            return f"ld {reg(y)},{reg(z)}"
        if x == 2:
            return f"{_ALU[y]}{reg(z)}"
        if x == 0:
            if z == 0:
                if y == 0:
                    return "nop"
                if y == 1:
                    return "ex af,af'"
                if y == 2:
                    d = self.disp()
                    return f"djnz {self.target(self.origin + self.at + d)}"
                d = self.disp()
                destination = self.target(self.origin + self.at + d)
                return f"jr {destination}" if y == 3 else f"jr {_CC[y - 4]},{destination}"
            if z == 1:
                hl = self._index(prefix, "hl")
                return f"ld {self._index(prefix, _RP[p])},{self._value(self.imm())}" if q == 0 else f"add {hl},{self._index(prefix, _RP[p])}"
            if z == 2:
                hl = self._index(prefix, "hl")
                forms = ["ld (bc),a", "ld a,(bc)", "ld (de),a", "ld a,(de)"]
                if p < 2:
                    return forms[p * 2 + q]
                address = self._value(self.imm())
                if p == 2:
                    return f"ld ({address}),{hl}" if q == 0 else f"ld {hl},({address})"
                return f"ld ({address}),a" if q == 0 else f"ld a,({address})"
            if z == 3:
                return f"{'inc' if q == 0 else 'dec'} {self._index(prefix, _RP[p])}"
            if z == 4:
                return f"inc {reg(y)}"
            if z == 5:
                return f"dec {reg(y)}"
            if z == 6:
                target = reg(y)
                return f"ld {target},{self.byte()}"
            return ["rlca", "rrca", "rla", "rra", "daa", "cpl", "scf", "ccf"][y]
        # x == 3
        if z == 0:
            return f"ret {_CC[y]}"
        if z == 1:
            if q == 0:
                return f"pop {self._index(prefix, _RP2[p])}"
            return ["ret", "exx", f"jp ({self._index(prefix, 'hl')})", f"ld sp,{self._index(prefix, 'hl')}"][p]
        if z == 2:
            return f"jp {_CC[y]},{self.target(self.imm())}"
        if z == 3:
            if y == 0:
                return f"jp {self.target(self.imm())}"
            if y == 2:
                return f"out (${self.byte():02X}),a"
            if y == 3:
                return f"in a,(${self.byte():02X})"
            return ["", "", "", "", f"ex (sp),{self._index(prefix, 'hl')}", "ex de,hl", "di", "ei"][y]
        if z == 4:
            return f"call {_CC[y]},{self.target(self.imm())}"
        if z == 5:
            if q == 0:
                return f"push {self._index(prefix, _RP2[p])}"
            if p == 0:
                return f"call {self.target(self.imm())}"
            return f"db ${op:02X}"
        if z == 6:
            return f"{_ALU[y]}{self.byte()}"
        if y == 5 and not self.adl:
            # bcall: rst 28h followed by the routine's address.
            routine = self.byte() | self.byte() << 8
            name = _classic_symbols().get(routine)
            return f"bcall({name or f'${routine:04X}'})"
        return f"rst ${y * 8:02X}"

    def _cb(self, prefix: int | None) -> str:
        d = self.disp() if prefix is not None else None
        op = self.byte()
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        target = self._index(prefix, "(hl)", d) if prefix is not None else _R[z]
        if x == 0:
            return f"{_ROT[y]} {target}"
        return f"{['', 'bit', 'res', 'set'][x]} {y},{target}"

    def _ed(self) -> str:
        op = self.byte()
        x, y, z, p, q = op >> 6, (op >> 3) & 7, op & 7, (op >> 4) & 3, (op >> 3) & 1
        if self.adl:
            ez80 = self._ez80(op)
            if ez80:
                return ez80
        if x == 1:
            if z == 0:
                return f"in {_R[y]},(c)" if y != 6 else "in (c)"
            if z == 1:
                return f"out (c),{_R[y]}" if y != 6 else "out (c),0"
            if z == 2:
                return f"{'sbc' if q == 0 else 'adc'} hl,{_RP[p]}"
            if z == 3:
                address = self._value(self.imm())
                return f"ld ({address}),{_RP[p]}" if q == 0 else f"ld {_RP[p]},({address})"
            if z == 4:
                return "neg"
            if z == 5:
                return "reti" if y == 1 else "retn"
            if z == 6:
                return f"im {_IM[y]}"
            return ["ld i,a", "ld r,a", "ld a,i", "ld a,r", "rrd", "rld", "nop", "nop"][y]
        if x == 2 and (y, z) in _BLOCK:
            return _BLOCK[(y, z)]
        return f"db $ED,${op:02X}"

    def _ez80(self, op: int) -> str | None:
        pairs = {0x07: "ld bc,(hl)", 0x0F: "ld (hl),bc", 0x17: "ld de,(hl)", 0x1F: "ld (hl),de", 0x27: "ld hl,(hl)",
                 0x2F: "ld (hl),hl", 0x31: "ld iy,(hl)", 0x37: "ld ix,(hl)", 0x3E: "ld (hl),iy", 0x3F: "ld (hl),ix",
                 0x4C: "mlt bc", 0x5C: "mlt de", 0x6C: "mlt hl", 0x7C: "mlt sp", 0x7D: "stmix", 0x7E: "rsmix",
                 0x56: "im 1", 0x7D + 0: "stmix"}
        if op in pairs:
            return pairs[op]
        lea = {0x02: "lea bc,ix", 0x03: "lea bc,iy", 0x12: "lea de,ix", 0x13: "lea de,iy", 0x22: "lea hl,ix",
               0x23: "lea hl,iy", 0x32: "lea ix,ix", 0x33: "lea iy,iy", 0x54: "lea ix,iy", 0x55: "lea iy,ix",
               0x65: "pea ix", 0x66: "pea iy"}
        if op in lea:
            return f"{lea[op]}{self.disp():+d}"
        if op == 0x64:
            return f"tst a,{self.byte()}"
        if op & 0xC7 == 0x00 and op != 0x30:
            return f"in0 {_R[(op >> 3) & 7]},(${self.byte():02X})"
        if op & 0xC7 == 0x01 and op != 0x31:
            return f"out0 (${self.byte():02X}),{_R[(op >> 3) & 7]}"
        return None

    def _value(self, value: int) -> str:
        names = _ce_symbols() if self.adl else {}
        if self.adl and value >= 0xD00000 and value in names:
            return names[value]
        if self.origin <= value < self.origin + len(self.code):
            return self.target(value)
        return self.addr(value)


def disassemble(code: bytes, origin: int, adl: bool) -> str:
    """A disassembly with labels at jump and call targets."""
    decoder = _Decoder(code, origin, adl)
    lines = []
    at = 0
    while at < len(code):
        length, text = decoder.decode(at)
        lines.append((origin + at, code[at:at + length], text))
        at += length
    starts = {address for address, _, _ in lines}
    symbols = _ce_symbols() if adl else _classic_symbols()
    width = 6 if adl else 4

    def name(address: int) -> str:
        if address in starts:
            return f"L_{address:0{width}X}"
        if adl and address in symbols:
            return symbols[address]
        return f"${address:0{width}X}"

    out = []
    for address, data, text in lines:
        if address in decoder.targets:
            out.append(f"L_{address:0{width}X}:")
        text = re.sub(r"@(\d+)", lambda match: name(int(match.group(1))), text)
        hexes = " ".join(f"{byte:02X}" for byte in data)
        out.append(f"    {text:<28}; {address:0{width}X}  {hexes}")
    return "\n".join(out) + "\n"


def hexdump(data: bytes) -> str:
    lines = []
    for at in range(0, len(data), 16):
        chunk = data[at:at + 16]
        text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{at:04X}  {' '.join(f'{byte:02X}' for byte in chunk):<48}  {text}")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ decompiling

def decompile_variable(variable: dict) -> tuple[str, str]:
    """(file suffix, text) for one variable."""
    kind, data = variable["type"], variable["data"]
    title = f"; {variable['name']}: {TYPE_NAMES.get(kind, f'type {kind:02X}h')}, {len(data)} bytes\n"
    if kind in PROGRAM_TYPES:
        body = _program_body(data)
        if body[:2] == b"\xEF\x7B":
            return ".asm", title + "; TI-84 Plus CE assembly program (eZ80, ADL mode)\n" + \
                disassemble(body[2:], CE_ORIGIN, True)
        if body[:2] == b"\xBB\x6D":
            return ".asm", title + "; TI-83 Plus/84 Plus assembly program (Z80)\n" + \
                disassemble(body[2:], CLASSIC_ORIGIN, False)
        source = detokenize(body)
        kind_name = "Axe source" if source.startswith(".") else "TI-BASIC"
        return ".txt", f"{title[2:]}{kind_name}:\n\n{source}\n"
    return ".txt", title[2:] + hexdump(data)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, help="a TI variable file, such as a .8xp program or a .8xv AppVar")
    parser.add_argument("-o", "--output", type=Path,
                        help="where to write (default: next to FILE, as NAME.asm or NAME.txt); - prints it")


def run(args: argparse.Namespace) -> int:
    variables = read_variables(args.file)
    if not variables:
        raise CompileError(f"{args.file} holds no variables")
    for variable in variables:
        suffix, text = decompile_variable(variable)
        if args.output is not None and str(args.output) == "-":
            print(text)
            continue
        name = re.sub(r"[^\w]", "_", variable["name"]) or args.file.stem
        output = args.output if args.output is not None and len(variables) == 1 else \
            args.file.with_name(f"{name}{suffix}")
        output.write_text(text, encoding="utf-8")
        print(f"Wrote {output}")
    return 0
