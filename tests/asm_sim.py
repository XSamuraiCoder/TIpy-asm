"""A small interpreter for the assembly TIpy-asm generates, used only by tests.

It models Z80 and eZ80 ADL registers closely enough to catch real bugs (the
upper byte of HL survives ``ld l,a``, and flags follow the CPU's rules), and
stubs the OS calls the compiler uses. It is a model, not an emulator: it proves
the generated logic, not that the OS or the hardware agrees with that model.
"""

from __future__ import annotations

import re

from ti84asm.compiler import Compiler

VRAM = 0xD40000
# Code is modeled as one address per instruction, in each CPU's address space.
LAYOUT = {"ce": {"code": 0x100000, "data": 0x200000, "stack": 0x3F0000, "heap": 0xD10000, "archive": 0x0C0000,
                 "exit": 0xFFFFF0},
          "classic": {"code": 0x1000, "data": 0x8000, "stack": 0xF000, "heap": 0xC000, "exit": 0xFFF0}}
CONSTANTS = {"ti.lcdBpp16": 0x2D, "ti.mpLcdCtrl": 0xE30018, "ti.AppVarObj": 0x15, "AppVarObj": 0x15, "YOffset": 0x9000,
             "ti.ProgObj": 5, "ti.ProtProgObj": 6, "plotSScreen": 0x9340,
             "ti.AppObj": 0x14, "ti.OP1": 0xD005F8, "ti.OP3": 0xD0060E}
PAIRS = {"b": ("bc", 8), "c": ("bc", 0), "d": ("de", 8), "e": ("de", 0), "h": ("hl", 8), "l": ("hl", 0)}
WIDE = {"hl", "de", "bc", "ix", "sp"}


class Timeout(Exception):
    pass


class Sim:
    def __init__(self, assembly: str, target: str, keys=(), held=(), appvars=None, hooks=None):
        self.target = target
        self.bits = 24 if target == "ce" else 16
        self.mask = (1 << self.bits) - 1
        self.word_bytes = self.bits // 8
        self.mem: dict[int, int] = {}
        self.labels: dict[str, int] = {}
        self.code: list[tuple[str, list[str]]] = []
        self.keys, self.held = list(keys), set(held)
        # label -> function(sim); stands in for a routine the model cannot run, such as flash writes.
        self.hooks = dict(hooks or {})
        self.appvars = {name: {"addr": None, "archived": False, "data": bytes(data), "name": name}
                        for name, data in (appvars or {}).items()}
        self.output = ""
        self.texts: list[tuple[str, int, int]] = []
        self.pixels: dict[tuple[int, int], int] = {}
        self.op1 = b""
        self.layout = LAYOUT[target]
        self.heap = self.layout["heap"]
        self.archive_heap = self.layout.get("archive", self.layout["heap"] + 0x1000)
        self.port_mask = 0xFF
        # Registers start with junk so code relying on a stale upper byte fails.
        self.r = {name: 0xAAAAAA & self.mask for name in ("hl", "de", "bc", "ix")}
        self.a = 0xAA
        self.sp = self.layout["stack"]
        self.S = self.Z = self.C = self.PV = False
        self.exit_sp = None
        self._assemble(assembly)
        for appvar in self.appvars.values():
            self._store_appvar(appvar)

    # ------------------------------------------------------------- assembly
    def _assemble(self, text: str) -> None:
        pending_data: list[tuple[int, list[str], int]] = []
        data_at = self.layout["data"]
        code_base = self.layout["code"]
        started = False
        waiting: list[str] = []
        for raw in text.splitlines():
            line = raw.split(";", 1)[0].strip()
            if not started:
                if line == "start:":
                    started = True
                    self.labels["start"] = code_base
                continue
            while True:
                match = re.match(r"([A-Za-z_][\w.]*):\s*(.*)", line)
                if not match:
                    break
                waiting.append(match.group(1))
                line = match.group(2)
            if not line:
                continue        # a label alone on its line names whatever comes next
            words = line.split(None, 1)
            mnemonic, rest = words[0], (words[1] if len(words) > 1 else "")
            operands = [item.strip() for item in rest.split(",")] if rest else []
            is_data = mnemonic in ("db", ".db", ".dw", "dw")
            for label in waiting:
                self.labels[label] = data_at if is_data else code_base + len(self.code)
            waiting = []
            if is_data:
                size = 2 if mnemonic in (".dw", "dw") else 1
                pending_data.append((data_at, operands, size))
                data_at += sum(len(item) - 2 if item[:1] in ("'", '"') else size for item in operands)
            else:
                self.code.append((mnemonic, operands))
        for address, operands, size in pending_data:
            at = address
            for operand in operands:
                if operand[:1] in ("'", '"'):
                    for char in operand[1:-1]:
                        self.mem[at] = ord(char)
                        at += 1
                    continue
                value = self.value(operand)
                for index in range(size):
                    self.mem[at + index] = (value >> (8 * index)) & 0xFF
                at += size
        self.instructions = len(self.code)

    def value(self, text: str) -> int:
        text = text.strip()
        if text in CONSTANTS:
            return CONSTANTS[text]
        if re.search(r"[*()]|(?<=\w)-", text):
            # Arithmetic such as 320*240*2-2: resolve each term, then evaluate digits and operators only.
            term = r"\$[0-9A-Fa-f]+|[0-9][0-9A-Fa-f]*h\b|[A-Za-z_][\w.]*|\d+"
            expression = re.sub(term, lambda match: str(self.value(match.group())), text)
            if not re.fullmatch(r"[\d\s+\-*()]+", expression):
                raise KeyError(f"unsupported expression {text!r}")
            return eval(expression)
        if "+" in text and not text.startswith("+"):
            left, right = text.split("+", 1)
            return self.value(left) + self.value(right)
        if text.startswith("$"):
            return int(text[1:], 16)
        if re.fullmatch(r"[0-9][0-9A-Fa-f]*h", text):
            return int(text[:-1], 16)
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        if text in self.labels:
            return self.labels[text]
        raise KeyError(f"unknown symbol {text!r}")

    # --------------------------------------------------------------- memory
    def read(self, address: int, size: int = 1) -> int:
        address &= 0xFFFFFF
        if self.target == "ce" and address & 0xFF0000 == 0xF50000:
            # Keypad registers repeat every 0x100 bytes. A requested scan finishes at
            # once, so the mode register reads as idle.
            register = address & 0xFF
            if 0x10 <= register < 0x20 and not register % 2:
                group = (register - 0x10) // 2
                return sum(1 << ((code - 1) & 7) for code in self.held if 7 - ((code - 1) >> 3) == group)
            return 0
        return sum(self.mem.get(address + index, 0) << (8 * index) for index in range(size))

    def write(self, address: int, value: int, size: int = 1) -> None:
        address &= 0xFFFFFF
        for index in range(size):
            self.mem[address + index] = (value >> (8 * index)) & 0xFF

    def vram(self, x: int, y: int) -> int:
        return self.read(VRAM + (y * 320 + x) * 2, 2)

    def word(self, label: str) -> int:
        value = self.read(self.labels[label], self.word_bytes)
        return value - (1 << self.bits) if value >> (self.bits - 1) else value

    def lit_pixels(self) -> set[tuple[int, int]]:
        """Pixels drawn to the CE's VRAM, or set on the classic screen model."""
        if self.target == "classic":
            return {point for point, color in self.pixels.items() if color}
        found = set()
        for address, value in self.mem.items():
            if VRAM <= address < VRAM + 153600 and value:
                offset = (address - VRAM) // 2
                found.add((offset % 320, offset // 320))
        return found

    # ------------------------------------------------------------ registers
    def get(self, name: str) -> int:
        if name == "a":
            return self.a
        if name in WIDE:
            return self.sp if name == "sp" else self.r[name]
        pair, shift = PAIRS[name]
        return (self.r[pair] >> shift) & 0xFF

    def set(self, name: str, value: int) -> None:
        if name == "a":
            self.a = value & 0xFF
        elif name == "sp":
            self.sp = value & self.mask if self.target == "classic" else value & 0xFFFFFF
        elif name in WIDE:
            self.r[name] = value & self.mask
        else:
            pair, shift = PAIRS[name]
            self.r[pair] = (self.r[pair] & ~(0xFF << shift)) | ((value & 0xFF) << shift)

    def source(self, operand: str) -> int:
        if operand in PAIRS or operand == "a" or operand in WIDE:
            return self.get(operand)
        if operand == "(hl)":
            return self.read(self.r["hl"])
        if operand == "(de)":
            return self.read(self.r["de"])
        match = re.fullmatch(r"\(ix(?:\+(\d+))?\)", operand)
        if match:
            return self.read(self.r["ix"] + int(match.group(1) or 0))
        if operand.startswith("("):
            return self.read(self.value(operand[1:-1]))
        return self.value(operand)

    def flags8(self, value: int, carry: bool | None = None) -> None:
        value &= 0xFF
        self.S, self.Z = bool(value & 0x80), value == 0
        self.PV = bin(value).count("1") % 2 == 0
        if carry is not None:
            self.C = carry

    def condition(self, code: str) -> bool:
        return {"z": self.Z, "nz": not self.Z, "c": self.C, "nc": not self.C, "m": self.S, "p": not self.S,
                "pe": self.PV, "po": not self.PV}[code]

    def push(self, value: int) -> None:
        self.sp -= self.word_bytes
        self.write(self.sp, value, self.word_bytes)

    def pop(self) -> int:
        value = self.read(self.sp, self.word_bytes)
        self.sp += self.word_bytes
        return value

    # ------------------------------------------------------------------ run
    def run(self, limit: int = 3_000_000) -> "Sim":
        exit_token = self.layout["exit"]
        self.push(exit_token)
        self.sp_start = self.sp
        code_base = self.layout["code"]
        pc = code_base
        exit_pc = self.labels.get("program_exit")
        steps = 0
        while pc != exit_token:
            steps += 1
            if steps > limit:
                raise Timeout(f"ran more than {limit} instructions")
            if pc == exit_pc:
                self.exit_sp = self.sp
            mnemonic, operands = self.code[pc - code_base]
            pc = self.step(mnemonic, operands, pc + 1)
        self.steps = steps
        return self

    def step(self, m: str, ops: list[str], next_pc: int) -> int:
        if m == "ld":
            self._ld(ops[0], ops[1])
        elif m == "push":
            self.push(self.get(ops[0]))
        elif m == "pop":
            self.set(ops[0], self.pop())
        elif m == "ex":
            self.r["de"], self.r["hl"] = self.r["hl"], self.r["de"]
        elif m == "add" and ops[0] == "hl":
            result = self.r["hl"] + self.get(ops[1])
            self.C = result > self.mask
            self.r["hl"] = result & self.mask
        elif m in ("sbc", "adc") and ops[0] == "hl":
            self._wide_carry_op(m, self.get(ops[1]))
        elif m == "inc" or m == "dec":
            self._step_register(m, ops[0])
        elif m in ("or", "and", "xor", "sub", "cp") or (m in ("add", "sbc") and ops[0] == "a"):
            self._alu(m, ops[-1])
        elif m == "rr":
            value = self.read(self.r["hl"])
            carry = value & 1
            value = (value >> 1) | (0x80 if self.C else 0)
            self.write(self.r["hl"], value)
            self.flags8(value, bool(carry))
        elif m == "sra":
            value = self.read(self.r["hl"])
            carry = value & 1
            value = (value >> 1) | (value & 0x80)
            self.write(self.r["hl"], value)
            self.flags8(value, bool(carry))
        elif m == "rlca":
            self.C = bool(self.a & 0x80)
            self.a = ((self.a << 1) | (self.a >> 7)) & 0xFF
        elif m == "cpl":
            self.a ^= 0xFF
        elif m == "scf":
            self.C = True
        elif m == "bit":
            self.Z = not (self.get(ops[1]) >> int(ops[0])) & 1
        elif m in ("jp", "jr"):
            if len(ops) == 1:
                return self.value(ops[0])
            return self.value(ops[1]) if self.condition(ops[0]) else next_pc
        elif m == "djnz":
            self.set("b", self.get("b") - 1)
            return self.value(ops[0]) if self.get("b") else next_pc
        elif m == "call" and ops[0] in self.hooks:
            self.hooks[ops[0]](self)
        elif m == "call":
            if ops[0].startswith("ti."):
                self.rom(ops[0][3:])
            else:
                self.push(next_pc)
                return self.value(ops[0])
        elif m == "ret":
            if not ops or self.condition(ops[0]):
                return self.pop()
        elif m.startswith("bcall("):
            self.rom(m[7:-1])
        elif m == "ldir":
            if not self.r["bc"]:
                raise AssertionError("LDIR with BC = 0 copies the whole address space and wipes RAM")
            while True:
                self.write(self.r["de"], self.read(self.r["hl"]))
                self.r["hl"] = (self.r["hl"] + 1) & self.mask
                self.r["de"] = (self.r["de"] + 1) & self.mask
                self.r["bc"] = (self.r["bc"] - 1) & self.mask
                if not self.r["bc"]:
                    break
        elif m == "out":
            self.port_mask = self.a
        elif m == "in":
            pressed = 0
            for code in self.held:
                if not (self.port_mask >> ((code - 1) >> 3)) & 1:
                    pressed |= 1 << ((code - 1) & 7)
            self.a = ~pressed & 0xFF
        elif m in ("nop", "ei", "di", "res", "set"):
            pass
        else:
            raise NotImplementedError(f"instruction {m} {ops}")
        return next_pc

    def _ld(self, dest: str, src: str) -> None:
        if dest == "iy":
            return              # IY always points at the OS flags; flag bits are not modelled
        if dest in ("hl", "de", "bc", "ix", "sp"):
            if src == "(hl)":
                self.set(dest, self.read(self.r["hl"], self.word_bytes))
            elif src.startswith("("):
                self.set(dest, self.read(self.value(src[1:-1]), self.word_bytes))
            else:
                self.set(dest, self.source(src))
        elif dest in PAIRS or dest == "a":
            if src.startswith("(iy"):
                self.set(dest, 0)
            else:
                self.set(dest, self.source(src))
        elif dest == "(hl)":
            if src in ("de", "hl", "bc"):
                self.write(self.r["hl"], self.get(src), self.word_bytes)
            else:
                self.write(self.r["hl"], self.source(src))
        elif dest == "(de)":
            self.write(self.r["de"], self.source(src))
        elif dest.startswith("(iy"):
            pass
        elif src in WIDE:
            self.write(self.value(dest[1:-1]), self.get(src), self.word_bytes)
        else:
            self.write(self.value(dest[1:-1]), self.source(src))

    def _wide_carry_op(self, m: str, operand: int) -> None:
        left, carry = self.r["hl"], int(self.C)
        sign = 1 << (self.bits - 1)
        if m == "sbc":
            raw = left - operand - carry
            self.PV = bool((left ^ operand) & (left ^ raw) & sign)
            self.C = raw < 0
        else:
            raw = left + operand + carry
            self.PV = bool(~(left ^ operand) & (left ^ raw) & sign)
            self.C = raw > self.mask
        result = raw & self.mask
        self.S, self.Z = bool(result & sign), result == 0
        self.r["hl"] = result

    def _step_register(self, m: str, operand: str) -> None:
        delta = 1 if m == "inc" else -1
        if operand in WIDE:
            self.set(operand, self.get(operand) + delta)
        elif operand == "(hl)":
            value = (self.read(self.r["hl"]) + delta) & 0xFF
            self.write(self.r["hl"], value)
            self.flags8(value)
        else:
            value = (self.get(operand) + delta) & 0xFF
            self.set(operand, value)
            self.flags8(value)

    def _alu(self, m: str, operand: str) -> None:
        right = self.source(operand)
        if m == "or":
            self.a |= right
            self.flags8(self.a, False)
        elif m == "and":
            self.a &= right
            self.flags8(self.a, False)
        elif m == "xor":
            self.a ^= right
            self.flags8(self.a, False)
        elif m == "add":
            raw = self.a + right
            self.a = raw & 0xFF
            self.flags8(self.a, raw > 0xFF)
        elif m == "sbc":
            raw = self.a - right - int(self.C)
            self.a = raw & 0xFF
            self.flags8(self.a, raw < 0)
        else:
            raw = self.a - right
            if m == "sub":
                self.a = raw & 0xFF
            self.flags8(raw, raw < 0)

    # ------------------------------------------------------------ OS stubs
    def _string(self, address: int) -> str:
        chars = []
        while (value := self.read(address)):
            chars.append(chr(value))
            address += 1
        return "".join(chars)

    def _store_appvar(self, appvar: dict) -> None:
        # RAM variables sit in RAM; archived ones in flash, below $D00000 on the CE.
        if appvar.get("archived"):
            address = self.archive_heap
            self.archive_heap += len(appvar["data"]) + 32
            # An archived variable's data follows a 9-byte header, the name's length, and the name.
            name_length = len(appvar.get("name", "HERO"))
            self.write(address + 9, name_length)
            address += 10 + name_length
            appvar["header"] = 10 + name_length
        else:
            address = self.heap
            self.heap += len(appvar["data"]) + 16
            appvar["header"] = 0
        appvar["addr"] = address
        self.write(address, len(appvar["data"]), 2)
        for offset, value in enumerate(appvar["data"]):
            self.write(address + 2 + offset, value)

    def archive(self, name: str) -> None:
        self.appvars[name]["archived"] = True
        self._store_appvar(self.appvars[name])

    def appvar(self, name: str) -> bytes:
        record = self.appvars[name]
        return bytes(self.read(record["addr"] + 2 + offset) for offset in range(self.read(record["addr"], 2)))

    def rom(self, name: str) -> None:
        name = name.removeprefix("_")
        if name == "GetCSC":
            self.a = self.keys.pop(0) if self.keys else 0
            if not self.keys and getattr(self, "_idle_keys", 0) > 100000:
                raise Timeout("program is waiting for a key the test did not provide")
            self._idle_keys = getattr(self, "_idle_keys", 0) + 1
        elif name == "PutS":
            self.output += self._string(self.r["hl"])
        elif name == "NewLine":
            self.output += "\n"
        elif name == "Mov9ToOP1":
            self.op1 = bytes(self.read(self.r["hl"] + index) for index in range(9))
        elif name == "ChkFindSym":
            record = self.appvars.get(self.op1[1:].split(b"\0")[0].decode())
            self.C = record is None
            if record:
                self.r["de"] = record["addr"] - record["header"]
                # Classic reports the archive page in B; on the CE, code must check the address instead.
                self.set("b", (1 if record["archived"] else 0) if self.target == "classic" else 0xAA)
        elif name == "CreateAppVar":
            label = self.op1[1:].split(b"\0")[0].decode()
            record = {"addr": None, "archived": False, "data": bytes(self.r["hl"]), "name": label}
            self.appvars[label] = record
            self._store_appvar(record)
            self.r["de"] = record["addr"]
        elif name == "MemSet":
            # As in OS 5.8.5: ld (hl),a / push hl / pop de / inc de / dec bc / ldir.
            self.write(self.r["hl"], self.a)
            self.r["de"] = (self.r["hl"] + 1) & self.mask
            self.r["bc"] = (self.r["bc"] - 1) & self.mask
            self.step("ldir", [], 0)
        elif name == "DelVarArc":
            del self.appvars[self.op1[1:].split(b"\0")[0].decode()]
        elif name == "os.FontDrawText":
            pointer = self.read(self.sp, self.word_bytes)
            x = self.read(self.sp + self.word_bytes, self.word_bytes)
            y = self.read(self.sp + 2 * self.word_bytes, self.word_bytes)
            self.texts.append((self._string(pointer), x, y))
        elif name == "boot.ClearVRAM":
            for address in [a for a in self.mem if VRAM <= a < VRAM + 153600]:
                del self.mem[address]
        elif name == "IPoint":
            self.pixels[(self.get("b"), 63 - self.get("c"))] = self.get("d")
        elif name == "ILine":
            self._classic_line()
        elif name in ("FillRect", "ClearRect"):
            self._classic_rect(1 if name == "FillRect" else 0)
        elif name in ("DrawRectBorder", "EraseRectBorder"):
            self._classic_border(1 if name == "DrawRectBorder" else 0)
        elif name == "GrBufClr":
            self.pixels.clear()
        elif name in ("ClrScrn", "HomeUp", "DrawStatusBar", "RunIndicOff", "GrBufCpy", "SetNorm_Vals", "os.SetDrawFGColor"):
            pass
        else:
            raise NotImplementedError(f"OS routine {name}")

    def _classic_rect(self, color: int) -> None:
        y0, x0, y1, x1 = self.get("h"), self.get("l"), self.get("d"), self.get("e")
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.pixels[(x, y)] = color

    def _classic_border(self, color: int) -> None:
        y0, x0, y1, x1 = self.get("h"), self.get("l"), self.get("d"), self.get("e")
        for x in range(x0, x1 + 1):
            self.pixels[(x, y0)] = self.pixels[(x, y1)] = color
        for y in range(y0, y1 + 1):
            self.pixels[(x0, y)] = self.pixels[(x1, y)] = color

    def _classic_line(self) -> None:
        x1, y1, x2, y2 = self.get("b"), 63 - self.get("c"), self.get("d"), 63 - self.get("e")
        color = self.get("h")
        dx, sx = abs(x2 - x1), 1 if x1 < x2 else -1
        dy, sy = -abs(y2 - y1), 1 if y1 < y2 else -1
        error = dx + dy
        while True:
            self.pixels[(x1, y1)] = color
            if x1 == x2 and y1 == y2:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x1 += sx
            if twice <= dx:
                error += dx
                y1 += sy


def run_program(source: str, target: str = "ce", **kwargs) -> tuple[Sim, Compiler]:
    """Compile and run a program; return the finished simulator and its compiler."""
    limit = kwargs.pop("limit", 3_000_000)
    compiler = Compiler("TEST", target, source_dir=kwargs.pop("source_dir", None))
    sim = Sim(compiler.compile(source), target, **kwargs)
    sim.compiler = compiler
    sim.run(limit)
    return sim, compiler


def variable(sim: Sim, compiler: Compiler, name: str) -> int:
    return sim.word(compiler.variables[name])
