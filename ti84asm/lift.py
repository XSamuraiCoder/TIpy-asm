"""Lift a Z80 or eZ80 program to Python: the decompiler's best effort at source.

Machine code has no variables, types, or loops, only registers, memory, and
jumps, so the Python keeps that shape while reading as code:

- Code is found by following the program from its start through jumps and
  calls, so data in the program is not mistaken for instructions.
- Each call target is a function. A function with no jumps inside it is plain
  straight-line Python; one with jumps runs through a small ``goto`` dispatcher,
  since Python has no goto.
- Registers are variables (a, bc, de, hl, ix, iy, sp); the 8-bit halves b, c, d,
  e, h, l are read and written inside their pairs. Memory is mem8[...] and
  memw[...] (16-bit words on classic calculators, 24-bit on the CE).
- A compare followed by a conditional jump becomes ``if a == 5:``; flags are kept
  in zf/cf/sf only when an instruction in between would change what they test.
- OS calls are named: bcall("PutS") on classic calculators, ti.PutS() on the CE.
- An instruction the lifter does not model stays as asm("..."), so nothing is
  dropped silently.

The result describes what the program does; it is not a TIpy program, because
TIpy's Python has no registers or raw memory.
"""

from __future__ import annotations

import keyword
import re

from .decompile import _ce_symbols, _classic_symbols, _Decoder

# Names the lifted program defines itself.
_RESERVED = {"a", "b", "c", "d", "e", "h", "l", "bc", "de", "hl", "ix", "iy", "sp", "zf", "cf", "sf", "pvf",
             "new_cf", "goto", "mem8", "memw", "push", "pop", "ldir", "lddr", "ldi", "ldd", "bcall", "ti",
             "call", "jump", "port_in", "port_out", "asm", "main"}

_REG8 = {"a", "b", "c", "d", "e", "h", "l", "ixh", "ixl", "iyh", "iyl", "i", "r"}
_HALVES = {"b": ("bc", 8), "c": ("bc", 0), "d": ("de", 8), "e": ("de", 0), "h": ("hl", 8), "l": ("hl", 0),
           "ixh": ("ix", 8), "ixl": ("ix", 0), "iyh": ("iy", 8), "iyl": ("iy", 0)}
_PAIRS = {"af", "bc", "de", "hl", "sp", "ix", "iy"}
_CONDITIONS = {"z": "zf", "nz": "not zf", "c": "cf", "nc": "not cf", "m": "sf", "p": "not sf",
               "pe": "pvf", "po": "not pvf"}
_ALU = {"add": "+", "adc": "+", "sub": "-", "sbc": "-", "and": "&", "or": "|", "xor": "^", "cp": "-"}


class _Flags:
    """The flags as Python expressions, valid until a register they read changes."""

    def __init__(self):
        self.exprs: dict[str, str] = {}
        self.reads: set[str] = set()

    def set(self, exprs: dict[str, str], reads: set[str]) -> None:
        self.exprs = dict(exprs)
        self.reads = set(reads)


class _Lifter:
    def __init__(self, code: bytes, origin: int, adl: bool):
        self.code, self.origin, self.adl = code, origin, adl
        self.mask = 0xFFFFFF if adl else 0xFFFF
        self.width = 6 if adl else 4
        self.decoder = _Decoder(code, origin, adl)
        self.symbols = _ce_symbols() if adl else _classic_symbols()
        self.used_symbols: dict[str, int] = {}
        self.instructions: dict[int, tuple[int, str]] = {}
        self.functions: list[int] = []

    # ------------------------------------------------------------- discovery
    def inside(self, address: int) -> bool:
        return self.origin <= address < self.origin + len(self.code)

    def decode(self, address: int) -> tuple[int, str]:
        if address not in self.instructions:
            self.instructions[address] = self.decoder.decode(address - self.origin)
        return self.instructions[address]

    @staticmethod
    def targets(text: str) -> list[int]:
        return [int(value) for value in re.findall(r"@(\d+)", text)]

    def explore(self) -> None:
        """Find code by following it from the start; call targets become functions."""
        pending, seen, functions = [self.origin], set(), [self.origin]
        while pending:
            address = pending.pop()
            while self.inside(address) and address not in seen:
                seen.add(address)
                length, text = self.decode(address)
                mnemonic = text.split(" ", 1)[0]
                for target in self.targets(text):
                    if self.inside(target):
                        pending.append(target)
                        if mnemonic == "call" and target not in functions:
                            functions.append(target)
                if self._ends_flow(text):
                    break
                address += length
        self.reachable = seen
        self.functions = functions

    @staticmethod
    def _ends_flow(text: str) -> bool:
        parts = text.split(" ", 1)
        mnemonic, operands = parts[0], (parts[1] if len(parts) > 1 else "")
        if mnemonic in ("ret", "reti", "retn") and not operands:
            return True
        if mnemonic in ("jp", "jr") and "," not in operands:
            return True
        return mnemonic == "halt"

    def blocks_of(self, entry: int) -> list[int]:
        """The starts of the blocks reachable from entry without following calls."""
        leaders, pending, seen = {entry}, [entry], set()
        while pending:
            address = pending.pop()
            while self.inside(address) and address not in seen:
                seen.add(address)
                length, text = self.decode(address)
                mnemonic = text.split(" ", 1)[0]
                if mnemonic in ("jp", "jr", "djnz"):
                    for target in self.targets(text):
                        if self.inside(target):
                            leaders.add(target)
                            pending.append(target)
                if self._ends_flow(text):
                    break
                address += length
        self.block_seen = seen
        return sorted(address for address in leaders if address in seen)

    # ------------------------------------------------------------- operands
    def name(self, address: int) -> str:
        if self.inside(address):
            return f"L_{address:0{self.width}X}"
        if address in self.symbols:
            return self.symbol(self.symbols[address], address)
        return f"0x{address:0{self.width}X}"

    def symbol(self, name: str, address: int) -> str:
        python = re.sub(r"\W", "_", name.removeprefix("ti.").removeprefix("_"))
        if python in _RESERVED or python[:1].isdigit() or python.startswith("L_") or keyword.iskeyword(python):
            python = f"os_{python}"      # never shadow a register, a helper, or a label
        self.used_symbols[python] = address
        return python

    def number(self, text: str) -> str:
        text = text.strip()
        if text.startswith("@"):
            address = int(text[1:])
            return f"0x{address:0{self.width}X}" if self.inside(address) else self.name(address)
        if text.startswith("$"):
            return f"0x{text[1:]}"
        if text.startswith("ti."):
            address = next((value for value, name in self.symbols.items() if name == text), None)
            return self.symbol(text, address or 0)
        if re.fullmatch(r"-?\d+", text):
            return text
        return text

    def size(self, operand: str) -> int:
        """1 for an 8-bit operand, 2 for a word, 0 when the other side decides."""
        if operand in _REG8:
            return 1
        if operand in _PAIRS:
            return 2
        return 0

    def address_of(self, operand: str) -> str | None:
        """The address of a memory operand such as (hl), (ix+5), or ($1234)."""
        if not (operand.startswith("(") and operand.endswith(")")):
            return None
        inner = operand[1:-1]
        match = re.fullmatch(r"(ix|iy)([+-]\d+)?", inner)
        if match:
            offset = match.group(2) or ""
            return f"{match.group(1)}{' + ' + offset[1:] if offset.startswith('+') else ' - ' + offset[1:] if offset else ''}"
        if inner in ("hl", "bc", "de", "sp"):
            return inner
        return self.number(inner)

    def read(self, operand: str, size: int) -> str:
        if operand in _HALVES:
            pair, shift = _HALVES[operand]
            return f"({pair} >> {shift} & 0xFF)" if shift else f"({pair} & 0xFF)"
        if operand in _REG8 or operand in _PAIRS:
            return operand
        address = self.address_of(operand)
        if address is not None:
            return f"mem8[{address}]" if size == 1 else f"memw[{address}]"
        return self.number(operand)

    def write(self, operand: str, value: str, size: int) -> list[str]:
        if operand in _HALVES:
            pair, shift = _HALVES[operand]
            keep = self.mask & ~(0xFF << shift)
            return [f"{pair} = {pair} & 0x{keep:X} | ({value}) << {shift}" if shift
                    else f"{pair} = {pair} & 0x{keep:X} | ({value})"]
        if operand in _REG8 or operand in _PAIRS:
            return [f"{operand} = {value}"]
        address = self.address_of(operand)
        if address is not None:
            return [f"mem8[{address}] = {value}" if size == 1 else f"memw[{address}] = {value}"]
        return [f"asm({('ld ' + operand + ',...')!r})"]

    @staticmethod
    def writes(operand: str) -> set[str]:
        if operand in _HALVES:
            return {_HALVES[operand][0]}
        if operand in _REG8 or operand in _PAIRS:
            return {operand}
        return {"mem"} if operand.startswith("(") else set()

    @staticmethod
    def reads_of(expression: str) -> set[str]:
        found = set(re.findall(r"\b(a|bc|de|hl|sp|ix|iy|zf|cf|sf)\b", expression))
        if "mem" in expression:
            found.add("mem")
        return found

    # ------------------------------------------------------------- one instruction
    def lift(self, text: str, flags: _Flags, follows: str) -> list[str]:
        """Python statements for one instruction. follows is the next instruction's text."""
        parts = text.split(" ", 1)
        mnemonic = parts[0]
        operands = [operand.strip() for operand in parts[1].split(",")] if len(parts) > 1 else []
        word = self.mask

        def flush(changed: set[str]) -> list[str]:
            """Store the flags before an instruction changes what they read."""
            if not flags.exprs or not (changed & flags.reads):
                return []
            stored = [f"{name} = {expr}" for name, expr in flags.exprs.items() if expr not in (name,)]
            flags.set({name: name for name in flags.exprs}, set(flags.exprs))
            return stored

        def set_flags(exprs: dict[str, str]) -> None:
            reads = set()
            for expr in exprs.values():
                reads |= self.reads_of(expr)
            flags.set(exprs, reads)

        if mnemonic.startswith("bcall("):
            routine = mnemonic[6:-1]
            name = routine.removeprefix("_") if not routine.startswith("$") else routine
            lines = flush({"a", "bc", "de", "hl", "mem"}) + [f'bcall("{name}")']
            flags.set({}, set())              # the OS routine leaves its own flags
            return lines
        if mnemonic == "ld":
            target, source = operands
            size = self.size(target) or self.size(source) or 1
            value = self.read(source, size)
            if source == "i" or source == "r":
                return [f"a = {source}  # interrupt state"]
            return flush(self.writes(target)) + self.write(target, value, size)
        if mnemonic in ("push", "pop"):
            register = operands[0]
            if mnemonic == "push":
                return [f"push({register})"]
            return flush({register}) + [f"{register} = pop()"]
        if mnemonic == "ex":
            if operands == ["de", "hl"]:
                return flush({"de", "hl"}) + ["de, hl = hl, de"]
            return [f"asm({text!r})"]
        if mnemonic in ("inc", "dec"):
            target = operands[0]
            sign = "+" if mnemonic == "inc" else "-"
            if self.size(target) == 2:
                return flush({target}) + self.write(target, f"({target} {sign} 1) & 0x{word:X}", 2)
            value = f"({self.read(target, 1)} {sign} 1) & 0xFF"
            lines = flush(self.writes(target)) + self.write(target, value, 1)
            set_flags({"zf": f"{self.read(target, 1)} == 0"})
            return lines
        if mnemonic in _ALU and (len(operands) == 1 or operands[0] == "a"):
            source = operands[-1]
            value = self.read(source, 1)
            symbol = _ALU[mnemonic]
            if mnemonic == "cp":
                set_flags({"zf": f"a == {value}", "cf": f"a < {value}"})
                return []
            if mnemonic in ("and", "or", "xor"):
                if mnemonic == "or" and source == "a":
                    set_flags({"zf": "a == 0", "cf": "False"})
                    return []
                lines = flush({"a"}) + [f"a = a {symbol} {value}"]
                set_flags({"zf": "a == 0", "cf": "False"})
                return lines
            carry = " + cf" if mnemonic == "adc" else " - cf" if mnemonic == "sbc" else ""
            borrow = f"a < {value}" if mnemonic in ("sub", "sbc") else f"a + {value}{carry} > 0xFF"
            lines = flush({"a", "cf"}) + [f"cf = {borrow}", f"a = (a {symbol} {value}{carry}) & 0xFF"]
            set_flags({"zf": "a == 0", "cf": "cf"})
            return lines
        if mnemonic in ("add", "adc", "sbc") and operands and operands[0] in ("hl", "ix", "iy"):
            target, source = operands
            if mnemonic == "add":
                return flush({target}) + [f"{target} = ({target} + {source}) & 0x{word:X}"]
            carry_known_clear = flags.exprs.get("cf") == "False"
            carry = "" if carry_known_clear else (" + cf" if mnemonic == "adc" else " - cf")
            symbol = "+" if mnemonic == "adc" else "-"
            top = self.width * 4 - 1
            # Overflow, for signed compares (jp pe/po), from the result and the value it had before.
            before = f"(({target} {'+' if symbol == '-' else '-'} {source}) & 0x{word:X})"
            overflow = (f"(({before} ^ {source}) & ({before} ^ {target})) >> {top} & 1" if symbol == "-"
                        else f"(~({before} ^ {source}) & ({before} ^ {target})) >> {top} & 1")
            if mnemonic == "sbc" and carry_known_clear:
                # "or a / sbc hl,de" compares: keep the compare readable when a jump follows.
                if follows.split(" ", 1)[0] in ("jp", "jr", "ret", "call") and "," in follows:
                    lines = flush({target}) + [f"{target} = ({target} - {source}) & 0x{word:X}"]
                    set_flags({"zf": f"{target} == 0", "cf": f"{target} + {source} > 0x{word:X}",
                               "sf": f"{target} >> {top} & 1", "pvf": overflow})
                    return lines
            lines = flush({target, "cf"}) + [f"cf = {target} {'<' if symbol == '-' else '+'} {source}{carry}"
                                             + ("" if symbol == "-" else f" > 0x{word:X}"),
                                             f"{target} = ({target} {symbol} {source}{carry}) & 0x{word:X}"]
            set_flags({"zf": f"{target} == 0", "cf": "cf", "sf": f"{target} >> {top} & 1", "pvf": overflow})
            return lines
        if mnemonic in ("cpl", "neg"):
            value = "a ^ 0xFF" if mnemonic == "cpl" else "-a & 0xFF"
            lines = flush({"a"}) + [f"a = {value}"]
            if mnemonic == "neg":
                set_flags({"zf": "a == 0"})
            return lines
        if mnemonic == "bit":
            bit, target = operands
            set_flags({"zf": f"not {self.read(target, 1)} >> {bit} & 1"})
            return []
        if mnemonic in ("set", "res"):
            bit, target = operands
            value = self.read(target, 1)
            new = f"{value} | 0x{1 << int(bit):02X}" if mnemonic == "set" else f"{value} & 0x{0xFF ^ (1 << int(bit)):02X}"
            return flush(self.writes(target)) + self.write(target, new, 1)
        if mnemonic in ("srl", "sla", "sra", "rr", "rl", "rrca", "rlca", "rra", "rla"):
            target = operands[0] if operands else "a"
            value = self.read(target, 1)
            new = {"srl": f"{value} >> 1", "sla": f"{value} << 1 & 0xFF", "sra": f"{value} >> 1 | {value} & 0x80",
                   "rr": f"{value} >> 1 | cf << 7", "rra": f"{value} >> 1 | cf << 7",
                   "rl": f"{value} << 1 & 0xFF | cf", "rla": f"{value} << 1 & 0xFF | cf",
                   "rrca": f"{value} >> 1 | ({value} & 1) << 7", "rlca": f"{value} << 1 & 0xFF | {value} >> 7"}[mnemonic]
            out_bit = f"{value} & 1" if mnemonic in ("srl", "sra", "rr", "rra", "rrca") else f"{value} >> 7"
            lines = flush(self.writes(target) | {"cf"}) + [f"new_cf = {out_bit}"] + self.write(target, new, 1) + \
                ["cf = new_cf"]
            set_flags({"zf": f"{self.read(target, 1)} == 0", "cf": "cf"})
            return lines
        if mnemonic in ("ldir", "lddr", "ldi", "ldd"):
            return flush({"bc", "de", "hl", "mem"}) + [f"hl, de, bc = {mnemonic}(hl, de, bc)"]
        # Only in a,(n) and out (n),r; the (c) forms and in0/out0 stay as asm().
        if mnemonic == "in" and len(operands) == 2 and operands[0] == "a" and operands[1] != "(c)":
            return flush({"a"}) + [f"a = port_in({self.number(operands[1][1:-1])})"]
        if mnemonic == "out" and len(operands) == 2 and operands[0] != "(c)" and operands[1] in ("a", "b", "c", "d", "e", "h", "l"):
            return [f"port_out({self.number(operands[0][1:-1])}, {self.read(operands[1], 1)})"]
        if mnemonic == "mlt":
            pair = operands[0]
            return flush({pair}) + [f"{pair} = ({pair} >> 8 & 0xFF) * ({pair} & 0xFF)"]
        if mnemonic in ("scf", "ccf"):
            lines = flush({"cf"})
            set_flags({**flags.exprs, "cf": "True" if mnemonic == "scf" else f"not ({flags.exprs.get('cf', 'cf')})"})
            return lines
        if mnemonic in ("di", "ei", "nop", "halt", "im"):
            return [f"# {text}"]
        return [f"asm({text!r})"]

    # ------------------------------------------------------------- control flow
    def condition(self, code: str, flags: _Flags) -> str:
        flag = _CONDITIONS[code]
        negate = flag.startswith("not ")
        name = flag.removeprefix("not ")
        expr = flags.exprs.get(name, name)
        if expr in ("False", "True"):
            value = expr == "True"
            return str(value != negate)
        return f"not ({expr})" if negate else expr

    def function(self, entry: int) -> list[str]:
        starts = self.blocks_of(entry)
        loops_to_entry = any(entry in self.targets(self.decode(address)[1]) and
                             self.decode(address)[1].split(" ", 1)[0] in ("jp", "jr", "djnz")
                             for address in self.block_seen)
        straight = len(starts) == 1 and not loops_to_entry
        lines = [f"def {self.name(entry)}():"]
        body_indent = "    " if straight else "            "
        if not straight:
            lines += [f"    goto = {self.name(entry)!r}", "    while True:"]
        for index, start in enumerate(starts):
            if not straight:
                lines.append(f"        {'if' if index == 0 else 'elif'} goto == {self.name(start)!r}:")
            flags = _Flags()
            address = start
            body = []
            while True:
                length, text = self.decode(address)
                next_address = address + length
                follows = self.decode(next_address)[1] if self.inside(next_address) else ""
                body += self.control(text, flags, follows, next_address, starts, straight)
                if self._ends_flow(text):
                    break
                address = next_address
                if address in starts:
                    body.append(f"goto = {self.name(address)!r}")
                    body.append("continue")
                    break
                if not self.inside(address) or address not in self.block_seen:
                    body.append("return  # runs past the code that was found")
                    break
            lines += [body_indent + line for line in (body or ["pass"])]
        if not straight:
            lines.append("        else:")
            lines.append("            raise RuntimeError(goto)")
        return lines

    def control(self, text: str, flags: _Flags, follows: str, after: int, starts: list[int], straight: bool) -> list[str]:
        parts = text.split(" ", 1)
        mnemonic = parts[0]
        operands = [operand.strip() for operand in parts[1].split(",")] if len(parts) > 1 else []
        if mnemonic in ("jp", "jr", "djnz", "call", "ret"):
            condition = None
            if mnemonic == "djnz":
                lines = ["bc = bc & 0x{0:X} | ((bc >> 8) - 1 & 0xFF) << 8".format(self.mask & ~0xFF00)]
                condition, operand = "bc >> 8 & 0xFF", operands[0]
            elif mnemonic != "ret" and len(operands) == 2:
                lines = []
                condition, operand = self.condition(operands[0], flags), operands[1]
            elif mnemonic == "ret" and operands:
                lines = []
                condition, operand = self.condition(operands[0], flags), None
            else:
                lines = []
                operand = operands[0] if operands else None
            if mnemonic == "ret":
                action = ["return"]
            elif mnemonic == "call":
                if condition is None:
                    flags.set({}, set())      # the routine leaves its own flags
                target = self.targets(text)
                if target and self.inside(target[0]):
                    action = [f"{self.name(target[0])}()"]
                elif target:
                    callee = self.name(target[0])
                    action = [f"ti.{callee}()" if self.adl and not callee.startswith("0x") else f"call({callee})"]
                else:
                    action = [f"asm({text!r})"]
            elif operand and operand.startswith("("):
                action = [f"jump({operand[1:-1]})  # an address computed at runtime", "return"]
            else:
                target = self.targets(text)
                # Follow jumps that only jump on, so the goto names where the code really is.
                for _ in range(16):
                    if not target or not self.inside(target[0]):
                        break
                    hop = self.decode(target[0])[1]
                    if hop.split(" ", 1)[0] not in ("jp", "jr") or "," in hop or not self.targets(hop):
                        break
                    if self.targets(hop)[0] not in starts:
                        break
                    target = self.targets(hop)
                if target and target[0] in starts and not straight:
                    action = [f"goto = {self.name(target[0])!r}", "continue"]
                elif target and self.inside(target[0]):
                    action = [f"return {self.name(target[0])}()  # a jump into another function"]
                else:
                    action = [f"jump({self.name(target[0]) if target else operand})", "return"]
            if condition is None:
                return lines + action
            if condition == "True":
                return lines + action
            if condition == "False":
                return lines
            return lines + [f"if {condition}:"] + ["    " + line for line in action]
        return self.lift(text, flags, follows)

    def program(self, name: str) -> str:
        if not self.code:
            return f'"""{name}: an empty program, so there is nothing to decompile."""\n'
        self.explore()
        functions = []
        for entry in self.functions:
            functions += self.function(entry) + ["", ""]
        size = "24-bit" if self.adl else "16-bit"
        header = [
            f'"""{name}, decompiled from {"eZ80 (TI-84 Plus CE)" if self.adl else "Z80 (TI-83 Plus/84 Plus)"} machine code by tipy-asm.',
            "",
            f"Registers are variables; memory is mem8[] and memw[] ({size} words). Each call target is a",
            "function, and code with jumps runs through a goto dispatcher. asm('...') marks an instruction",
            "the lifter does not model. The helpers at the end stand in for the calculator.",
            '"""',
            "",
            "a = bc = de = hl = ix = iy = 0",
            f"sp = 0x{0xD1A87E if self.adl else 0xFFC5:X}",
            "zf = cf = sf = pvf = False",
        ]
        if self.used_symbols:
            header += ["", "# OS addresses this program uses, from the include files"]
            header += [f"{symbol} = 0x{address:0{self.width}X}" for symbol, address in sorted(self.used_symbols.items())]
        unreached = len(self.code) - sum(self.instructions[address][0] for address in self.reachable)
        header += ["", f"# {len(self.reachable)} instructions found as code; {unreached} bytes are data or unreached.",
                   "", ""]
        footer = _RUNTIME.format(size=3 if self.adl else 2, mask=self.mask)
        globals_line = "    global a, bc, de, hl, ix, iy, sp, zf, cf, sf, pvf"
        body = []
        for line in functions:
            body.append(line)
            if line.startswith("def "):
                body.append(globals_line)
        body = _fill_empty_blocks(body)
        return "\n".join(header + body) + footer + f"\n\nif __name__ == '__main__':\n    {self.name(self.origin)}()\n"


def _fill_empty_blocks(lines: list[str]) -> list[str]:
    """Add pass to any block left with only comments, such as one that lifted to # halt."""
    out = []
    for i, line in enumerate(lines):
        out.append(line)
        if not line.rstrip().endswith(":") or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        for following in lines[i + 1:]:
            if not following.strip():
                continue
            deeper = len(following) - len(following.lstrip()) > indent
            if deeper and following.lstrip().startswith("#"):
                continue
            if not deeper:
                out.append(" " * (indent + 4) + "pass")
            break
        else:
            out.append(" " * (indent + 4) + "pass")
    return out


_RUNTIME = '''
# --------------------------------------------------------------------------
# Stand-ins for the calculator, so the code above is plain Python.

class _Memory:
    def __init__(self, width):
        self.bytes, self.width = {{}}, width

    def __getitem__(self, address):
        if self.width == 1:
            return self.bytes.get(address, 0)
        return sum(self.bytes.get(address + i, 0) << 8 * i for i in range(self.width))

    def __setitem__(self, address, value):
        for i in range(self.width):
            self.bytes[address + i] = value >> 8 * i & 0xFF


mem8 = _Memory(1)
memw = _Memory({size})
memw.bytes = mem8.bytes


def push(value):
    global sp
    sp = (sp - {size}) & 0x{mask:X}
    memw[sp] = value


def pop():
    global sp
    value = memw[sp]
    sp = (sp + {size}) & 0x{mask:X}
    return value


def ldir(hl, de, bc):
    while True:
        mem8[de] = mem8[hl]
        hl, de, bc = hl + 1, de + 1, bc - 1
        if bc == 0:
            return hl, de, bc


def lddr(hl, de, bc):
    while True:
        mem8[de] = mem8[hl]
        hl, de, bc = hl - 1, de - 1, bc - 1
        if bc == 0:
            return hl, de, bc


def ldi(hl, de, bc):
    mem8[de] = mem8[hl]
    return hl + 1, de + 1, bc - 1


def ldd(hl, de, bc):
    mem8[de] = mem8[hl]
    return hl - 1, de - 1, bc - 1


def bcall(name):
    print("OS:", name)


class _OS:
    def __getattr__(self, name):
        return lambda: print("OS:", name)


ti = _OS()


def call(address):
    print("call", hex(address))


def jump(address):
    print("jump", address)


def port_in(port):
    return 0


def port_out(port, value):
    pass


def asm(text):
    print("not lifted:", text)
'''


def lift_program(code: bytes, origin: int, adl: bool, name: str) -> str:
    """Python for a program's machine code."""
    return _Lifter(code, origin, adl).program(name)
