"""Translate C-like calculator source (CEdev C, ICE) into TIpy's Python subset.

This is a real, if small, parser: statements are read from tokens and printed
with correct indentation. Anything it cannot express is not guessed at. It
becomes a ``# TODO(convert)`` comment in the output and an entry in the
conversion's warnings, so a converted project either builds or says why not.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r"""
    (?P<newline>\n)
  | (?P<space>[ \t\r\f]+)
  | (?P<string>"(?:\\.|[^"\\\n])*")
  | (?P<char>'(?:\\.|[^'\\\n])')
  | (?P<number>0[xX][0-9a-fA-F]+[uUlL]*|0[bB][01]+[uUlL]*|\d+[uUlL]*)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<op>\+\+|--|<<=|>>=|&&|\|\||==|!=|<=|>=|<<|>>|\+=|-=|\*=|/=|%=|&=|\|=|\^=|->|[-+*/%<>=!&|^~?:;,.(){}\[\]])
""", re.VERBOSE)

TYPE_WORDS = {
    "void", "char", "short", "int", "long", "float", "double", "signed", "unsigned", "bool", "_Bool",
    "byte", "word", "uint8_t", "uint16_t", "uint24_t", "uint32_t", "int8_t", "int16_t", "int24_t", "int32_t",
    "size_t", "kb_key_t", "sk_key_t", "gfx_sprite_t", "ti_var_t",
}
QUALIFIERS = {"const", "static", "extern", "volatile", "register", "inline"}
_AUG_ASSIGN = {"+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}

# name -> (python call, whether the current drawing color is appended)
_CALLS = {
    "gfx_Begin": ("graphics.begin", False), "gfx_End": ("graphics.end", False),
    "gfx_ZeroScreen": ("graphics.clear", False), "gfx_FillScreen": ("graphics.fill_screen", False),
    "gfx_SetPixel": ("graphics.pixel", True), "gfx_FillRectangle": ("graphics.fill_rect", True),
    "gfx_FillRectangle_NoClip": ("graphics.fill_rect", True), "gfx_Rectangle": ("graphics.rectangle", True),
    "gfx_Rectangle_NoClip": ("graphics.rectangle", True), "gfx_Line": ("graphics.line", True),
    "gfx_Line_NoClip": ("graphics.line", True), "gfx_Circle": ("graphics.circle", True),
    "gfx_Circle_NoClip": ("graphics.circle", True), "gfx_FillCircle": ("graphics.fill_circle", True),
    "gfx_FillCircle_NoClip": ("graphics.fill_circle", True), "gfx_HorizLine": ("graphics.horiz_line", True),
    "gfx_HorizLine_NoClip": ("graphics.horiz_line", True), "gfx_VertLine": ("graphics.vert_line", True),
    "gfx_VertLine_NoClip": ("graphics.vert_line", True), "gfx_FillTriangle": ("graphics.triangle", True),
    "gfx_FillTriangle_NoClip": ("graphics.triangle", True), "gfx_PrintStringXY": ("graphics.text", False),
    "os_GetCSC": ("keyboard.get", False), "kb_Hit": ("keyboard.get", False), "delay": ("graphics.delay", False),
    "os_PutStrFull": ("print", False), "sqrt": ("math.sqrt", False), "abs": ("abs", False),
    "rand": ("_converted_rand", False), "srand": ("random.seed", False), "randInt": ("random.randint", False),
    # This example dialect's simpler drawing names.
    "gfx_DrawPixel": ("graphics.pixel", True), "gfx_DrawRectangle": ("graphics.rectangle", True),
    "gfx_DrawCircle": ("graphics.circle", True),
}
_COLOR_SETTERS = {"gfx_SetColor"}
_DROPPED_CALLS = {
    "gfx_SetDrawScreen": "the assembly backend always draws to the screen",
    "gfx_SetDrawBuffer": "the assembly backend always draws to the screen",
    "gfx_SwapDraw": "the assembly backend always draws to the screen",
    "gfx_Blit": "the assembly backend always draws to the screen",
    "gfx_BlitBuffer": "the assembly backend always draws to the screen",
    "gfx_SetTransparentColor": "AppVar sprites treat color 0 as transparent",
    "gfx_SetPalette": "the assembly backend draws RGB565 colors, not a palette",
    "gfx_SetDefaultPalette": "the assembly backend draws RGB565 colors, not a palette",
    "gfx_SetTextFGColor": "pass a color to graphics.text() instead",
    "gfx_SetTextBGColor": "graphics.text() has no background color",
    "gfx_SetTextScale": "graphics.text() has one size",
    "gfx_SetMonospaceFont": "graphics.text() has one font",
    "os_ClrHome": "clear the screen with graphics.clear() if needed",
    "kb_Scan": "keyboard calls scan by themselves",
    "kb_Reset": "keyboard calls scan by themselves",
    "dbg_printf": "debug output is not supported",
}
_COLORS = {"gfx_black": "BLACK", "gfx_white": "WHITE", "gfx_red": "RED", "gfx_green": "GREEN", "gfx_blue": "BLUE",
           "gfx_yellow": "YELLOW", "gfx_orange": "ORANGE", "gfx_purple": "PURPLE", "gfx_pink": "PINK"}
_KEYS = {"sk_Down": "DOWN", "sk_Left": "LEFT", "sk_Right": "RIGHT", "sk_Up": "UP", "sk_Enter": "ENTER",
         "sk_Clear": "CLEAR", "sk_2nd": "SECOND", "sk_Mode": "MODE", "sk_Del": "DEL", "sk_Alpha": "ALPHA",
         "sk_Add": "ADD", "sk_Sub": "SUB", "sk_Mul": "MUL", "sk_Div": "DIV", "sk_Yequ": "YEQU",
         **{f"sk_{digit}": f"KEY_{digit}" for digit in range(10)}}
_SCREEN = {"GFX_LCD_WIDTH": "graphics.width", "LCD_WIDTH": "graphics.width",
           "GFX_LCD_HEIGHT": "graphics.height", "LCD_HEIGHT": "graphics.height"}
_RAND_HELPER = "def _converted_rand():\n    return random.randrange(32767)\n\n"


@dataclass
class Conversion:
    code: str
    warnings: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    defines: list[tuple[str, str]] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    uses_main: bool = False


class _Unsupported(Exception):
    pass


def _strip_comments(source: str) -> str:
    """Remove comments, keeping strings and line numbers intact."""
    out, index, length = [], 0, len(source)
    while index < length:
        pair = source[index:index + 2]
        char = source[index]
        if pair == "//":
            while index < length and source[index] != "\n":
                index += 1
        elif pair == "/*":
            end = source.find("*/", index + 2)
            end = length if end < 0 else end + 2
            out.append("\n" * source.count("\n", index, end))
            index = end
        elif char in "\"'":
            start = index
            index += 1
            while index < length and source[index] != char and source[index] != "\n":
                index += 2 if source[index] == "\\" else 1
            index += 1
            out.append(source[start:index])
        else:
            out.append(char)
            index += 1
    return "".join(out)


@dataclass
class _Token:
    kind: str
    text: str
    line: int


def _tokenize(source: str) -> list[_Token]:
    tokens, index, line = [], 0, 1
    while index < len(source):
        match = _TOKEN.match(source, index)
        if match is None:
            raise _Unsupported(f"line {line}: cannot read {source[index]!r}")
        kind = match.lastgroup
        if kind == "newline":
            tokens.append(_Token("newline", "\n", line))
            line += 1
        elif kind != "space":
            tokens.append(_Token(kind, match.group(), line))
        index = match.end()
    return tokens


class _Translator:
    def __init__(self, source: str, newline_ends_statement: bool):
        self.newline_ends_statement = newline_ends_statement
        self.result = Conversion("")
        self.out: list[str] = []
        self.imports: set[str] = set()
        self.uses_color = False
        self.uses_rand = False
        self.tokens = self._preprocess(_strip_comments(source))
        self.pos = 0
        self.source_lines = source.splitlines()
        self.global_names: set[str] = set()

    # --------------------------------------------------------- preprocessor
    def _preprocess(self, source: str) -> list[_Token]:
        lines = []
        for number, line in enumerate(source.split("\n"), 1):
            stripped = line.strip()
            if not stripped.startswith("#"):
                lines.append(line)
                continue
            lines.append("")
            include = re.match(r'#\s*include\s*"([^"]+)"', stripped)
            define = re.match(r"#\s*define\s+([A-Za-z_]\w*)\s+(.+)$", stripped)
            if include:
                self.result.includes.append(include.group(1))
            elif define:
                self.result.defines.append((define.group(1), define.group(2).strip()))
            elif re.match(r"#\s*define\s+\w+\s*\(", stripped):
                self.warn(number, f"macro with arguments not converted: {stripped}")
            elif re.match(r"#\s*(if|ifdef|ifndef|else|elif|endif|pragma)", stripped):
                if not re.search(r"_H_*\b|pragma once", stripped) and "endif" not in stripped:
                    self.warn(number, f"preprocessor conditional ignored: {stripped}")
        return _tokenize("\n".join(lines))

    def warn(self, line: int, message: str) -> None:
        self.result.warnings.append(f"line {line}: {message}")

    # -------------------------------------------------------------- reading
    def peek(self, skip_newlines: bool = True) -> _Token | None:
        index = self.pos
        while index < len(self.tokens):
            token = self.tokens[index]
            if token.kind != "newline" or not skip_newlines:
                return token
            index += 1
        return None

    def next(self) -> _Token:
        token = self.peek()
        if token is None:
            raise _Unsupported("unexpected end of file")
        self.pos = self.tokens.index(token, self.pos) + 1
        return token

    def accept(self, text: str) -> bool:
        token = self.peek()
        if token is not None and token.text == text:
            self.next()
            return True
        return False

    def expect(self, text: str) -> None:
        token = self.next()
        if token.text != text:
            raise _Unsupported(f"line {token.line}: expected {text!r} but found {token.text!r}")

    def balanced(self, opening: str, closing: str) -> list[_Token]:
        """Read tokens after an opening bracket up to its matching closing one."""
        depth, tokens = 1, []
        while True:
            token = self.next()
            if token.text == opening:
                depth += 1
            elif token.text == closing:
                depth -= 1
                if not depth:
                    return tokens
            tokens.append(token)

    def statement_tokens(self) -> list[_Token]:
        """Read up to ';' (consumed), or a newline in dialects without semicolons."""
        tokens, depth = [], 0
        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            if token.kind == "newline":
                self.pos += 1
                if self.newline_ends_statement and depth == 0 and tokens:
                    return tokens
                continue
            if token.text in "([":
                depth += 1
            elif token.text in ")]":
                depth -= 1
            elif token.text == ";" and depth == 0:
                self.pos += 1
                return tokens
            elif token.text == "}" and depth == 0:
                return tokens
            tokens.append(token)
            self.pos += 1
        return tokens

    def skip_block_or_statement(self) -> None:
        if self.accept("{"):
            self.balanced("{", "}")
        else:
            self.statement_tokens()

    # --------------------------------------------------------------- output
    def emit(self, depth: int, text: str) -> None:
        self.out.append("    " * depth + text)

    def todo(self, depth: int, line: int, reason: str) -> None:
        original = self.source_lines[line - 1].strip() if 0 < line <= len(self.source_lines) else ""
        self.warn(line, f"{reason}: {original}")
        self.emit(depth, f"# TODO(convert): {reason}: {original}")
        self.emit(depth, "pass")

    # ---------------------------------------------------------- expressions
    def split_arguments(self, tokens: list[_Token]) -> list[list[_Token]]:
        parts, current, depth = [], [], 0
        for token in tokens:
            if token.text in "([":
                depth += 1
            elif token.text in ")]":
                depth -= 1
            if token.text == "," and depth == 0:
                parts.append(current)
                current = []
            else:
                current.append(token)
        if current:
            parts.append(current)
        return parts

    def expr(self, tokens: list[_Token]) -> str:
        """Translate an expression's tokens to Python text."""
        tokens = self._strip_parens(tokens)
        question = self._top_level(tokens, "?")
        if question is not None:
            depth, colon = 0, None
            for index in range(question + 1, len(tokens)):
                text = tokens[index].text
                if text in "([?":
                    depth += 1
                elif text in ")]":
                    depth -= 1
                elif text == ":":
                    if depth == 0:
                        colon = index
                        break
                    depth -= 1
            if colon is None:
                raise _Unsupported(f"line {tokens[question].line}: malformed ?: expression")
            return (f"({self.expr(tokens[question + 1:colon])} if {self.expr(tokens[:question])} "
                    f"else {self.expr(tokens[colon + 1:])})")
        out: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            text = token.text
            following = tokens[index + 1].text if index + 1 < len(tokens) else ""
            if self._is_cast(tokens, index):
                index = self._after_paren(tokens, index)
                continue
            if token.kind == "name" and following == "(":
                end = self._after_paren(tokens, index + 1)
                out.append(self.call(text, tokens[index + 2:end - 1], token.line))
                index = end
                continue
            if text == "(":
                end = self._after_paren(tokens, index)
                out.append(f"({self.expr(tokens[index + 1:end - 1])})")
                index = end
                continue
            if text in ("++", "--", "->") or (text == "." and token.kind == "op"):
                raise _Unsupported(f"line {token.line}: {text} inside an expression")
            if text == "=":
                raise _Unsupported(f"line {token.line}: assignment inside an expression")
            if text == "&" and (index == 0 or tokens[index - 1].text in "(,=" or tokens[index - 1].kind == "op"):
                raise _Unsupported(f"line {token.line}: pointers")
            if text == "*" and (index == 0 or (tokens[index - 1].kind == "op" and tokens[index - 1].text != ")")):
                raise _Unsupported(f"line {token.line}: pointers")
            if text == "sizeof":
                raise _Unsupported(f"line {token.line}: sizeof")
            out.append(self.atom(token))
            index += 1
        return " ".join(out).replace("( ", "(").replace(" )", ")").replace(" [ ", "[").replace(" ]", "]").replace("not  ", "not ")

    def atom(self, token: _Token) -> str:
        text = token.text
        if token.kind == "number":
            return re.sub(r"[uUlL]+$", "", text)
        if token.kind == "char":
            value = text[1:-1].encode().decode("unicode_escape")
            return str(ord(value))
        if token.kind == "string":
            return text
        if token.kind == "name":
            if text in ("true", "TRUE"):
                return "True"
            if text in ("false", "FALSE"):
                return "False"
            if text == "NULL":
                return "0"
            if text in _COLORS:
                self.imports.add("graphics")
                return f"graphics.{_COLORS[text]}"
            if text in _KEYS:
                self.imports.add("keyboard")
                return f"keyboard.{_KEYS[text]}"
            if text in _SCREEN:
                self.imports.add("graphics")
                return _SCREEN[text]
            return self.safe_name(text)
        return {"&&": "and", "||": "or", "!": "not", "/": "//"}.get(text, text)

    def safe_name(self, name: str) -> str:
        return name + "_" if keyword.iskeyword(name) else name

    def _strip_parens(self, tokens: list[_Token]) -> list[_Token]:
        while (len(tokens) >= 2 and tokens[0].text == "(" and self._after_paren(tokens, 0) == len(tokens)
               and not self._is_cast(tokens, 0)):
            tokens = tokens[1:-1]
        return tokens

    def _top_level(self, tokens: list[_Token], text: str) -> int | None:
        depth = 0
        for index, token in enumerate(tokens):
            if token.text in "([":
                depth += 1
            elif token.text in ")]":
                depth -= 1
            elif token.text == text and depth == 0:
                return index
        return None

    def _after_paren(self, tokens: list[_Token], start: int) -> int:
        depth = 0
        for index in range(start, len(tokens)):
            if tokens[index].text == "(":
                depth += 1
            elif tokens[index].text == ")":
                depth -= 1
                if not depth:
                    return index + 1
        raise _Unsupported(f"line {tokens[start].line}: unbalanced parentheses")

    def _is_cast(self, tokens: list[_Token], index: int) -> bool:
        if tokens[index].text != "(":
            return False
        end = self._after_paren(tokens, index)
        inner = tokens[index + 1:end - 1]
        return bool(inner) and end < len(tokens) and all(
            token.text in TYPE_WORDS or token.text in QUALIFIERS or token.text == "*" for token in inner)

    def call(self, name: str, argument_tokens: list[_Token], line: int) -> str:
        arguments = [self.expr(part) for part in self.split_arguments(argument_tokens)]
        if name in ("sizeof", "malloc", "free", "memcpy", "memset", "strlen", "strcpy", "printf", "sprintf"):
            raise _Unsupported(f"line {line}: {name}() has no TIpy equivalent")
        if name == "rand":
            self.uses_rand = True
            self.imports.add("random")
        mapping = _CALLS.get(name)
        if mapping is None:
            if name.startswith(("gfx_", "os_", "ti_", "kb_", "boot_", "fontlib_", "usb_", "sys_")):
                raise _Unsupported(f"line {line}: {name}() has no TIpy equivalent")
            return f"{self.safe_name(name)}({', '.join(arguments)})"
        python, uses_color = mapping
        if "." in python:
            self.imports.add(python.split(".")[0])
        if uses_color:
            arguments.append("_draw_color")
            self.uses_color = True
            self.imports.add("graphics")
        return f"{python}({', '.join(arguments)})"

    # ----------------------------------------------------------- statements
    def body(self, depth: int) -> None:
        """Translate the statement or block controlled by if/else/while/for."""
        start = len(self.out)
        next_on_line = self.peek(skip_newlines=False)
        if self.newline_ends_statement and (next_on_line is None or next_on_line.kind == "newline"):
            nearest = self.peek()
            if nearest is None or nearest.text != "{":
                self.emit(depth, "pass")     # `while (cond)` alone on a line waits.
                return
        if self.accept(";"):
            self.emit(depth, "pass")
            return
        if self.accept("{"):
            self.block(depth)
        else:
            self.statement(depth)
        if len(self.out) == start:
            self.emit(depth, "pass")

    def block(self, depth: int) -> None:
        while True:
            token = self.peek()
            if token is None:
                raise _Unsupported("unexpected end of file inside a block")
            if token.text == "}":
                self.next()
                return
            position = self.pos
            self.statement(depth)
            if self.pos == position:     # never loop on text no rule consumes
                self.next()

    def statement(self, depth: int) -> None:
        token = self.peek()
        if token is None:
            return
        checkpoint = self.pos
        try:
            self._statement(token, depth)
        except _Unsupported as problem:
            self.pos = checkpoint
            self.skip_statement()
            reason = re.sub(r"^line \d+: ", "", str(problem))
            self.todo(depth, token.line, f"not converted ({reason})")

    def skip_statement(self) -> None:
        token = self.peek()
        if token is None:
            return
        if token.text in ("if", "while", "for", "switch", "do", "else"):
            self.next()
            if self.peek() is not None and self.peek().text == "(":
                self.next()
                self.balanced("(", ")")
            self.skip_block_or_statement()
            if token.text == "do":
                self.statement_tokens()
            if token.text == "if" and self.peek() is not None and self.peek().text == "else":
                self.skip_statement()
        elif token.text == "{":
            self.next()
            self.balanced("{", "}")
        elif token.text in ("struct", "union", "enum", "typedef"):
            # Skip the braces whole, or the ';' inside them would end the skip early.
            while self.peek() is not None and self.peek().text not in ("{", ";"):
                self.next()
            if self.accept("{"):
                self.balanced("{", "}")
            self.statement_tokens()
        else:
            self.statement_tokens()

    def _statement(self, token: _Token, depth: int) -> None:
        text = token.text
        if text == "{":
            self.next()
            self.block(depth)
        elif text == ";":
            self.next()
        elif text == "if":
            self.next()
            self.expect("(")
            condition = self.expr(self.balanced("(", ")"))
            self.emit(depth, f"if {condition}:")
            self.body(depth + 1)
            following = self.peek()
            while following is not None and following.text == "else":
                self.next()
                after = self.peek()
                if after is not None and after.text == "if":
                    self.next()
                    self.expect("(")
                    condition = self.expr(self.balanced("(", ")"))
                    self.emit(depth, f"elif {condition}:")
                    self.body(depth + 1)
                    following = self.peek()
                else:
                    self.emit(depth, "else:")
                    self.body(depth + 1)
                    break
        elif text == "while":
            self.next()
            self.expect("(")
            condition = self.expr(self.balanced("(", ")"))
            self.emit(depth, f"while {condition}:")
            self.body(depth + 1)
        elif text == "do":
            self.next()
            self.emit(depth, "while True:")
            self.body(depth + 1)
            self.expect("while")
            self.expect("(")
            condition = self.expr(self.balanced("(", ")"))
            self.accept(";")
            self.emit(depth + 1, f"if not ({condition}):")
            self.emit(depth + 2, "break")
        elif text == "for":
            self._for(depth)
        elif text == "return":
            self.next()
            tokens = self.statement_tokens()
            self.emit(depth, f"return {self.expr(tokens)}" if tokens else "return")
        elif text in ("break", "continue"):
            self.next()
            self.statement_tokens()
            self.emit(depth, text)
        elif text in ("switch", "goto", "struct", "union", "enum", "typedef"):
            raise _Unsupported(f"line {token.line}: {text}")
        elif text in TYPE_WORDS or text in QUALIFIERS:
            self._declaration(depth)
        else:
            self._simple_statement(self.statement_tokens(), depth)

    def _for(self, depth: int) -> None:
        self.next()
        self.expect("(")
        header = self.balanced("(", ")")
        parts: list[list[_Token]] = [[]]
        for token in header:
            if token.text == ";":
                parts.append([])
            else:
                parts[-1].append(token)
        if len(parts) != 3:
            raise _Unsupported(f"line {header[0].line if header else 0}: for loop header")
        init, condition, step = parts
        while init and (init[0].text in TYPE_WORDS or init[0].text in QUALIFIERS):
            init = init[1:]
        simple = self._simple_range(init, condition, step)
        if simple:
            self.emit(depth, simple)
            self.body(depth + 1)
            return
        # A general for becomes a while, so `continue` would skip its step.
        line = header[0].line if header else 0
        if init:
            self._simple_statement(init, depth)
        self.emit(depth, f"while {self.expr(condition) if condition else 'True'}:")
        start = len(self.out)
        self.body(depth + 1)
        if any("continue" in out_line for out_line in self.out[start:]):
            self.warn(line, "for loop became a while loop; check that 'continue' still runs its step")
        if step:
            self._simple_statement(step, depth + 1)

    def _simple_range(self, init: list[_Token], condition: list[_Token], step: list[_Token]) -> str | None:
        """Recognize ``for (i = a; i < b; i++)`` and its stepped and downward forms."""
        if len(init) < 3 or init[0].kind != "name" or init[1].text != "=" or len(condition) < 3:
            return None
        name = init[0].text
        if condition[0].text != name or condition[1].text not in ("<", "<=", ">", ">="):
            return None
        amount = None
        if [token.text for token in step] == [name, "++"] or [token.text for token in step] == ["++", name]:
            amount = 1
        elif [token.text for token in step] == [name, "--"] or [token.text for token in step] == ["--", name]:
            amount = -1
        elif len(step) == 3 and step[0].text == name and step[1].text in ("+=", "-=") and step[2].kind == "number":
            value = int(re.sub(r"[uUlL]+$", "", step[2].text), 0)
            amount = value if step[1].text == "+=" else -value
        if not amount or (amount > 0) != (condition[1].text in ("<", "<=")):
            return None
        bound_tokens = condition[2:]
        # The bound must not change inside the loop for range() to be equivalent.
        if any(token.kind == "name" and not token.text.isupper() and token.text not in _SCREEN for token in bound_tokens):
            return None
        start, stop = self.expr(init[2:]), self.expr(bound_tokens)
        if condition[1].text == "<=":
            stop = f"{stop} + 1"
        elif condition[1].text == ">=":
            stop = f"{stop} - 1"
        arguments = f"{start}, {stop}" if amount == 1 else f"{start}, {stop}, {amount}"
        return f"for {self.safe_name(name)} in range({arguments}):"

    def _declaration(self, depth: int) -> None:
        tokens = self.statement_tokens()
        while tokens and (tokens[0].text in TYPE_WORDS or tokens[0].text in QUALIFIERS):
            tokens = tokens[1:]
        for part in self.split_arguments(tokens):
            if not part:
                continue
            if part[0].text == "*":
                raise _Unsupported(f"line {part[0].line}: pointers")
            name = part[0]
            if name.kind != "name":
                raise _Unsupported(f"line {name.line}: declaration")
            if len(part) > 1 and part[1].text == "[":
                self._array(part, depth)
            elif len(part) >= 3 and part[1].text == "=":
                self.emit(depth, f"{self.safe_name(name.text)} = {self.expr(part[2:])}")
            elif len(part) == 1:
                self.emit(depth, f"{self.safe_name(name.text)} = 0")
            else:
                raise _Unsupported(f"line {name.line}: declaration")

    def _array(self, part: list[_Token], depth: int) -> None:
        name = part[0]
        if depth:
            raise _Unsupported(f"line {name.line}: arrays must be global on assembly targets")
        close = next(index for index, token in enumerate(part) if token.text == "]")
        size = part[2:close]
        rest = part[close + 1:]
        if not rest and len(size) == 1 and size[0].kind == "number":
            self.emit(depth, f"{self.safe_name(name.text)} = [0] * {self.atom(size[0])}")
        elif rest and rest[0].text == "=" and rest[1].text == "{":
            values = [self.expr(item) for item in self.split_arguments(rest[2:-1])]
            self.emit(depth, f"{self.safe_name(name.text)} = [{', '.join(values)}]")
        else:
            raise _Unsupported(f"line {name.line}: this array declaration")

    def _simple_statement(self, tokens: list[_Token], depth: int) -> None:
        if not tokens:
            return
        line = tokens[0].line
        first, last = tokens[0].text, tokens[-1].text
        if last in ("++", "--") and len(tokens) >= 2:
            self.emit(depth, f"{self.expr(tokens[:-1])} {'+' if last == '++' else '-'}= 1")
            return
        if first in ("++", "--") and len(tokens) >= 2:
            self.emit(depth, f"{self.expr(tokens[1:])} {'+' if first == '++' else '-'}= 1")
            return
        if tokens[0].kind == "name" and len(tokens) >= 2 and tokens[1].text == "(":
            name = tokens[0].text
            if name in _COLOR_SETTERS:
                self.uses_color = True
                self.emit(depth, f"_draw_color = {self.expr(tokens[2:-1])}")
                return
            if name in _DROPPED_CALLS:
                self.warn(line, f"{name}() removed: {_DROPPED_CALLS[name]}")
                return
        depth_now = 0
        for index, token in enumerate(tokens):
            if token.text in "([":
                depth_now += 1
            elif token.text in ")]":
                depth_now -= 1
            elif depth_now == 0 and (token.text == "=" or token.text in _AUG_ASSIGN):
                target = self.expr(tokens[:index])
                value = self.expr(tokens[index + 1:])
                operator = "//=" if token.text == "/=" else token.text
                self.emit(depth, f"{target} {operator} {value}")
                return
        self.emit(depth, self.expr(tokens))

    # ------------------------------------------------------------ top level
    def _is_function_start(self) -> tuple[str, list[_Token]] | None:
        """If a function header starts here, consume it and return (name, parameters)."""
        start = self.pos
        words = []
        while True:
            token = self.peek()
            if token is None:
                break
            if token.text in TYPE_WORDS or token.text in QUALIFIERS or token.text in ("*", "function"):
                self.next()
                words.append(token)
            else:
                break
        name = self.peek()
        if name is None or name.kind != "name" or not words:
            self.pos = start
            return None
        self.next()
        opening = self.peek()
        if opening is None or opening.text != "(":
            self.pos = start
            return None
        self.next()
        return name.text, self.balanced("(", ")")

    def _parameters(self, tokens: list[_Token]) -> list[str]:
        names = []
        for part in self.split_arguments(tokens):
            texts = [token.text for token in part]
            if texts == ["void"] or not texts:
                continue
            if "*" in texts or "[" in texts:
                raise _Unsupported(f"line {part[0].line}: pointer parameters")
            names.append(self.safe_name(part[-1].text))
        return names

    def translate(self) -> Conversion:
        pieces: list[tuple[str, list[str]]] = []    # (kind, lines)
        while self.peek() is not None:
            token = self.peek()
            self.out = []
            if token.text == "}":        # unmatched; never stop making progress
                self.next()
                self.warn(token.line, "unmatched '}' ignored")
                continue
            header = self._is_function_start()
            if header is not None:
                following = self.peek()
                if following is not None and following.text == ";":      # a prototype
                    self.next()
                    continue
                name, parameter_tokens = header
                if following is None or following.text != "{":
                    if self.newline_ends_statement:
                        continue
                    self.todo(0, token.line, "not converted (unexpected text after function header)")
                    pieces.append(("code", self.out))
                    continue
                self.next()
                try:
                    parameters = self._parameters(parameter_tokens)
                except _Unsupported as problem:
                    self.balanced("{", "}")
                    self.todo(0, token.line, f"not converted ({re.sub(r'^line [0-9]+: ', '', str(problem))})")
                    pieces.append(("code", self.out))
                    continue
                self.result.functions.append(name)
                self.block(1)
                pieces.append(("function", [f"def {self.safe_name(name)}({', '.join(parameters)}):", *(self.out or ["    pass"])]))
            else:
                self.statement(0)
                pieces.append(("code", self.out))

        self.global_names = {match.group(1) for kind, lines in pieces if kind == "code" for line in lines
                             for match in [re.match(r"([A-Za-z_]\w*)\s*=[^=]", line)] if match}
        if self.uses_color:
            self.global_names.add("_draw_color")
        lines: list[str] = []
        for kind, block in pieces:
            if kind == "function":
                written = sorted({match.group(1) for line in block[1:]
                                  for match in [re.match(r"\s*([A-Za-z_]\w*)\s*(?:[-+*/%&|^]|//|<<|>>)?=[^=]", line)] if match}
                                 & self.global_names)
                lines.append(block[0])
                if written:
                    lines.append(f"    global {', '.join(written)}")
                lines.extend(block[1:])
                lines.append("")
            else:
                lines.extend(block)
        self.result.uses_main = "main" in self.result.functions
        header = []
        libraries = sorted(self.imports)
        if libraries:
            header.append(f"from ti84 import {', '.join(libraries)}")
        self.result.code = "\n".join(header) + ("\n\n" if header else "")
        if self.uses_rand:
            self.result.code += _RAND_HELPER
        if self.uses_color:
            self.result.code += "# gfx_SetColor() state; CEdev palette indices are not RGB565 colors.\n_draw_color = 0\n"
        self.result.code += "\n".join(lines).rstrip() + "\n"
        return self.result


def translate(source: str, newline_ends_statement: bool = False) -> Conversion:
    """Translate one C-like source file."""
    try:
        return _Translator(source, newline_ends_statement).translate()
    except _Unsupported as problem:
        message = str(problem)
        conversion = Conversion(f"# TODO(convert): this file could not be converted ({message})\n")
        conversion.warnings.append(f"file not converted: {message}")
        return conversion
