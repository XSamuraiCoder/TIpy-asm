"""Convert Axe Parser source to TIpy-asm Python, for the classic target.

Axe source is a TI-BASIC-style program, usually tokenized in a .8xp (its first
line is ".NAME"); a text file of the same commands works too. The converter
follows Axe's rules where they differ from Python's:

- Math runs strictly left to right with no precedence, so 1+2*3 is 9: every
  operation is parenthesized in that order.
- A-Z and θ are 16-bit variables (lowercase here, θ is theta); r1-r6 hold the
  arguments of sub().
- "Lbl X ... Return" is a subroutine that sub(X) calls: it becomes lbl_x().
- E1F is a hex number, πbinary a binary one, and 'A' a character code.

Commands TIpy has no match for (Goto, pointers and {} memory, sprites, the
homescreen cursor, and most of Axe's extended library) become TODO(convert)
comments and warnings, as the ICE converter does.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..tokens import detokenize
from .c_like import Conversion

_OPERATORS = {"+": "+", "-": "-", "*": "*", "/": "//", "^": "%", "=": "==", "≠": "!=", "<": "<", ">": ">",
              "≤": "<=", "≥": ">=", " and ": "&", " or ": "|", " xor ": "^"}
_VARIABLE = re.compile(r"[A-Zθ]$")


def read_axe(source: str | Path) -> str:
    """Axe source as text: a tokenized .8xp is detokenized, other files are read as text."""
    if isinstance(source, Path):
        data = source.read_bytes()
        if data[:8] in (b"**TI83F*", b"**TI73**"):
            length = data[72] | data[73] << 8
            return detokenize(data[74:74 + length])
        return data.decode("utf-8", errors="replace")
    return source


def _split_statements(text: str) -> list[str]:
    """Lines and ':'-separated statements, keeping strings whole."""
    statements = []
    for line in text.replace("\r", "").split("\n"):
        current, quoted = "", False
        for char in line:
            if char == '"':
                quoted = not quoted
            if char == ":" and not quoted:
                statements.append(current)
                current = ""
            else:
                current += char
        statements.append(current)
    return [statement.strip() for statement in statements]


class _Expression:
    """Turn one Axe expression into Python, left to right."""

    _TOKEN = re.compile(r'"[^"]*"?|\'.\'|ᴇ[0-9A-F]+|π[01]+|[0-9]+|getKey|rand|r[1-6]|L[1-6]|'
                        r'[A-Zθ]\(?|abs\(|min\(|max\(|√\(|sub\(|not\(|[(),{}→]|⁻|'
                        r' and | or | xor |[-+*/^=≠<>≤≥]|\S')

    def __init__(self, converter: "_Converter"):
        self.converter = converter

    def convert(self, text: str) -> str:
        self.tokens = [token for token in self._TOKEN.findall(text) if token.strip() or token.startswith(" ")]
        self.index = 0
        value = self._chain()
        if self.index < len(self.tokens):
            raise ValueError(f"unexpected {self.tokens[self.index]!r}")
        return value

    def _peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise ValueError("expression ends early")
        self.index += 1
        return token

    def _chain(self) -> str:
        value = self._operand()
        while self._peek() in _OPERATORS:
            operator = _OPERATORS[self._take()]
            value = f"({value} {operator} {self._operand()})"
        return value

    def _arguments(self) -> list[str]:
        values = []
        if self._peek() == ")":
            self._take()
            return values
        while True:
            values.append(self._chain())
            token = self._take() if self._peek() is not None else ")"
            if token == ")":
                return values
            if token != ",":
                raise ValueError(f"expected , or ) and found {token!r}")

    def _operand(self) -> str:
        token = self._take()
        if token == "(":
            value = self._chain()
            if self._peek() == ")":
                self._take()
            return value
        if token == "⁻":
            return f"(-{self._operand()})"
        if token.isdigit():
            return token
        if token.startswith("ᴇ"):
            return f"0x{token[1:]}"
        if token.startswith("π"):
            return f"0b{token[1:]}"
        if token.startswith("'") and len(token) == 3:
            return str(ord(token[1]))
        if token == "getKey":
            if self._peek() == "(":
                self._take()
                key = self._arguments()
                self.converter.uses("keyboard")
                return f"keyboard.is_down({key[0]})" if key else "keyboard.get()"
            self.converter.uses("keyboard")
            return "keyboard.get()"
        if token == "rand":
            self.converter.uses("random")
            return "random.randrange(65536)"
        if token in ("abs(", "min(", "max("):
            return f"{token}{', '.join(self._arguments())})"
        if token == "not(":
            return f"(not {self._arguments()[0]})"
        if token == "√(":
            self.converter.uses("math")
            return f"math.sqrt({self._arguments()[0]})"
        if token == "sub(":
            name, *arguments = self._arguments()
            return self.converter.sub_call(name, arguments)
        if re.fullmatch(r"r[1-6]", token):
            return token
        if _VARIABLE.match(token):
            return "theta" if token == "θ" else token.lower()
        raise ValueError(f"{token!r} is not something the converter knows")


class _Converter:
    def __init__(self):
        self.imports: set[str] = set()
        self.warnings: list[str] = []
        self.functions: dict[str, list[str]] = {}
        self.main: list[str] = []
        self.target = self.main
        self.depth = 0
        self.blocks: list[str] = []
        self.globals: set[str] = set()

    def uses(self, module: str) -> None:
        self.imports.add(module)

    def sub_call(self, name: str, arguments: list[str]) -> str:
        label = name.lower()
        if arguments:
            assigns = "; ".join(f"r{index + 1} = {value}" for index, value in enumerate(arguments))
            self.pending_before = getattr(self, "pending_before", []) + [assigns]
        return f"lbl_{label}()"

    def emit(self, line: str) -> None:
        for before in getattr(self, "pending_before", []):
            for part in before.split("; "):
                self.target.append("    " * (self.depth + 1) + part)
        self.pending_before = []
        self.target.append("    " * (self.depth + 1) + line)

    def todo(self, statement: str, why: str) -> None:
        self.emit(f"pass  # TODO(convert): {statement}  ({why})")
        self.warnings.append(f"{statement}: {why}")

    def expression(self, text: str, statement: str) -> str | None:
        try:
            return _Expression(self).convert(text)
        except ValueError as exc:
            self.todo(statement, str(exc))
            return None

    def statement(self, statement: str) -> None:
        if not statement:
            return
        if statement.startswith("."):
            if self.depth or self.target is not self.main or self.main:
                self.target.append("    " * (self.depth + 1) + "# " + statement[1:].strip())
            return
        if statement.startswith("Lbl "):
            label = statement[4:].strip().lower()
            self.target = self.functions.setdefault(label, [])
            self.depth = 0
            self.blocks.clear()
            return
        if statement == "Return":
            if self.depth == 0:
                self.emit("return")
                if self.target is not self.main:
                    self.target = []          # code after a routine's Return never runs
            else:
                self.emit("return")
            return
        for keyword, opener in (("!If ", "if not "), ("If ", "if "), ("While ", "while "), ("Repeat ", "while not ")):
            if statement.startswith(keyword):
                condition = self.expression(statement[len(keyword):], statement)
                if condition is not None:
                    self.emit(f"{opener}{condition}:")
                    self.depth += 1
                    self.blocks.append(keyword.strip())
                return
        if statement == "Else":
            if self.blocks and self.blocks[-1] in ("If", "!If"):
                self.depth -= 1
                self.emit("else:")
                self.depth += 1
            else:
                self.todo(statement, "Else outside an If")
            return
        if statement == "End":
            if self.blocks:
                self.blocks.pop()
                self.depth -= 1
            return
        if statement.startswith("For("):
            parts = statement[4:].rstrip(")").split(",")
            if len(parts) == 3 and _VARIABLE.match(parts[0].strip()):
                start, stop = (self.expression(part, statement) for part in parts[1:])
                if start is not None and stop is not None:
                    name = "theta" if parts[0].strip() == "θ" else parts[0].strip().lower()
                    self.emit(f"for {name} in range({start}, {stop} + 1):")
                    self.depth += 1
                    self.blocks.append("For")
                return
            self.todo(statement, "For( takes a variable, a start, and an end")
            return
        if "→" in statement:
            value, _, name = statement.rpartition("→")
            name = name.strip()
            if _VARIABLE.match(name) or re.fullmatch(r"r[1-6]", name):
                converted = self.expression(value, statement)
                if converted is not None:
                    variable = "theta" if name == "θ" else name.lower()
                    self.globals.add(variable)
                    self.emit(f"{variable} = {converted}")
            else:
                self.todo(statement, "only A-Z, θ, and r1-r6 can be stored to")
            return
        self.command(statement)

    def command(self, statement: str) -> None:
        simple = {"ClrDraw": ("graphics", "graphics.clear()"),
                  "DispGraph": (None, "pass  # DispGraph: TIpy shows each drawing at once")}
        if statement in simple:
            module, line = simple[statement]
            if module:
                self.uses(module)
            self.emit(line)
            return
        if statement in ("ClrHome", "DiagnosticOff", "DiagnosticOn", "Full", "Normal", "Fix 5", "Fix 4"):
            self.emit(f"pass  # {statement}: not needed in TIpy")
            return
        drawing = {"Pxl-On(": ("pixel", 2, "graphics.BLACK"), "Pxl-Off(": ("pixel", 2, "graphics.WHITE"),
                   "Line(": ("line", 4, "graphics.BLACK"), "Rect(": ("fill_rect", 4, "graphics.BLACK"),
                   "Circle(": ("circle", 3, "graphics.BLACK")}
        for opener, (method, count, color) in drawing.items():
            if statement.startswith(opener):
                arguments = self._call_arguments(statement, opener)
                if arguments is not None and len(arguments) == count:
                    self.uses("graphics")
                    self.emit(f"graphics.{method}({', '.join(arguments)}, {color})")
                elif arguments is not None:
                    self.todo(statement, f"{opener}) takes {count} values here")
                return
        if statement.startswith("Text("):
            match = re.fullmatch(r'Text\((.+?),(.+?),\s*"([^"]*)"?\)?', statement)
            if match:
                x, y = (self.expression(part, statement) for part in match.groups()[:2])
                if x is not None and y is not None:
                    self.uses("graphics")
                    text = match.group(3).replace("\\", "\\\\").replace('"', '\\"')
                    self.emit(f'graphics.text("{text}", {x}, {y})')
                return
            self.todo(statement, "Text( with a string literal is converted; other text is not")
            return
        if statement.startswith("Disp "):
            self._disp(statement)
            return
        if statement.startswith("Pause "):
            value = self.expression(statement[6:], statement)
            if value is not None:
                self.uses("graphics")
                self.emit(f"graphics.delay({value})")
            return
        if statement.startswith("Goto "):
            self.todo(statement, "Goto has no Python match; restructure it as a loop or sub()")
            return
        if statement.startswith("sub("):
            call = self.expression(statement, statement)
            if call is not None:
                self.emit(call)
            return
        self.todo(statement, "no TIpy match")

    def _call_arguments(self, statement: str, opener: str) -> list[str] | None:
        inner = statement[len(opener):]
        if inner.endswith(")"):
            inner = inner[:-1]
        values = []
        for part in self._split_commas(inner):
            value = self.expression(part, statement)
            if value is None:
                return None
            values.append(value)
        return values

    @staticmethod
    def _split_commas(text: str) -> list[str]:
        parts, depth, current, quoted = [], 0, "", False
        for char in text:
            if char == '"':
                quoted = not quoted
            if not quoted and char == "(":
                depth += 1
            if not quoted and char == ")":
                depth -= 1
            if char == "," and depth == 0 and not quoted:
                parts.append(current)
                current = ""
            else:
                current += char
        parts.append(current)
        return parts

    def _disp(self, statement: str) -> None:
        for item in self._split_commas(statement[5:]):
            item = item.strip()
            if item.startswith('"'):
                text = item.strip('"').replace("\\", "\\\\").replace('"', '\\"')
                self.emit(f'print("{text}")')
            elif item == "𝑖":
                self.emit('print("")')
            elif item.endswith("►Dec"):
                value = self.expression(item[:-4], statement)
                if value is not None:
                    self.emit(f"print({value})")
            else:
                self.todo(statement, "Disp shows strings and ►Dec numbers here")

    def code(self) -> str:
        imports = sorted(self.imports)
        lines = [f"from ti84 import {', '.join(imports)}", ""] if imports else []
        names = sorted(self.globals | {f"r{index}" for index in range(1, 7)})
        lines += [f"{name} = 0" for name in names] + [""]
        declaration = f"    global {', '.join(names)}"
        for label, body in self.functions.items():
            lines += ["", f"def lbl_{label}():", declaration, *(body or ["    pass"])]
        lines += ["", "", "def main():", declaration, *(self.main or ["    pass"])]
        return "\n".join(lines) + "\n"


def convert_axe(source: str | Path) -> Conversion:
    """Translate Axe source, a tokenized .8xp, or a Path to either, returning code and warnings."""
    converter = _Converter()
    for statement in _split_statements(read_axe(source)):
        converter.statement(statement)
    if converter.blocks:
        converter.warnings.append(f"{len(converter.blocks)} block(s) have no End")
    return Conversion(code=converter.code(), warnings=converter.warnings, uses_main=True,
                      functions=[f"lbl_{label}" for label in converter.functions])


def axe_to_python(source: str | Path) -> str:
    """Translate Axe source to Python source."""
    return convert_axe(source).code
