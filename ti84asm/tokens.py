"""TI-83 Plus / TI-84 Plus tokens: turn a tokenized program (TI-BASIC or Axe source) into text.

A program is a stream of one-byte tokens, plus two-byte tokens behind prefix
bytes (5Ch matrices, 5Dh lists, 5Eh equations, 60h pictures, 61h GDBs, 62h
statistics, 63h window variables, 7Eh graph formats, AAh strings, BBh and EFh
more commands). Tokens this table does not name come out as [XXXX].
"""

from __future__ import annotations

_ONE = {
    0x01: "►DMS", 0x02: "►Dec", 0x03: "►Frac", 0x04: "→", 0x05: "Boxplot", 0x06: "[", 0x07: "]", 0x08: "{",
    0x09: "}", 0x0A: "ʳ", 0x0B: "°", 0x0C: "⁻¹", 0x0D: "²", 0x0E: "ᵀ", 0x0F: "³", 0x10: "(", 0x11: ")",
    0x12: "round(", 0x13: "pxl-Test(", 0x14: "augment(", 0x15: "rowSwap(", 0x16: "row+(", 0x17: "*row(",
    0x18: "*row+(", 0x19: "max(", 0x1A: "min(", 0x1B: "R►Pr(", 0x1C: "R►Pθ(", 0x1D: "P►Rx(", 0x1E: "P►Ry(",
    0x1F: "median(", 0x20: "randM(", 0x21: "mean(", 0x22: "solve(", 0x23: "seq(", 0x24: "fnInt(",
    0x25: "nDeriv(", 0x27: "fMin(", 0x28: "fMax(", 0x29: " ", 0x2A: '"', 0x2B: ",", 0x2C: "𝑖", 0x2D: "!",
    0x2E: "CubicReg ", 0x2F: "QuartReg ", 0x3A: ".", 0x3B: "ᴇ", 0x3C: " or ", 0x3D: " xor ", 0x3E: ":",
    0x3F: "\n", 0x40: " and ", 0x5B: "θ", 0x5F: "prgm", 0x64: "Radian", 0x65: "Degree", 0x66: "Normal",
    0x67: "Sci", 0x68: "Eng", 0x69: "Float", 0x6A: "=", 0x6B: "<", 0x6C: ">", 0x6D: "≤", 0x6E: "≥",
    0x6F: "≠", 0x70: "+", 0x71: "-", 0x72: "Ans", 0x73: "Fix ", 0x74: "Horiz", 0x75: "Full", 0x76: "Func",
    0x77: "Param", 0x78: "Polar", 0x79: "Seq", 0x7A: "IndpntAuto", 0x7B: "IndpntAsk", 0x7C: "DependAuto",
    0x7D: "DependAsk", 0x7F: "▫", 0x80: "﹢", 0x81: "·", 0x82: "*", 0x83: "/", 0x84: "Trace",
    0x85: "ClrDraw", 0x86: "ZStandard", 0x87: "ZTrig", 0x88: "ZBox", 0x89: "Zoom In", 0x8A: "Zoom Out",
    0x8B: "ZSquare", 0x8C: "ZInteger", 0x8D: "ZPrevious", 0x8E: "ZDecimal", 0x8F: "ZoomStat",
    0x90: "ZoomRcl", 0x91: "PrintScreen", 0x92: "ZoomSto", 0x93: "Text(", 0x94: " nPr ", 0x95: " nCr ",
    0x96: "FnOn ", 0x97: "FnOff ", 0x98: "StorePic ", 0x99: "RecallPic ", 0x9A: "StoreGDB ", 0x9B: "RecallGDB ",
    0x9C: "Line(", 0x9D: "Vertical ", 0x9E: "Pt-On(", 0x9F: "Pt-Off(", 0xA0: "Pt-Change(", 0xA1: "Pxl-On(",
    0xA2: "Pxl-Off(", 0xA3: "Pxl-Change(", 0xA4: "Shade(", 0xA5: "Circle(", 0xA6: "Horizontal ",
    0xA7: "Tangent(", 0xA8: "DrawInv ", 0xA9: "DrawF ", 0xAB: "rand", 0xAC: "π", 0xAD: "getKey", 0xAE: "'",
    0xAF: "?", 0xB0: "⁻", 0xB1: "int(", 0xB2: "abs(", 0xB3: "det(", 0xB4: "identity(", 0xB5: "dim(",
    0xB6: "sum(", 0xB7: "prod(", 0xB8: "not(", 0xB9: "iPart(", 0xBA: "fPart(", 0xBC: "√(", 0xBD: "³√(",
    0xBE: "ln(", 0xBF: "e^(", 0xC0: "log(", 0xC1: "₁₀^(", 0xC2: "sin(", 0xC3: "sin⁻¹(", 0xC4: "cos(",
    0xC5: "cos⁻¹(", 0xC6: "tan(", 0xC7: "tan⁻¹(", 0xC8: "sinh(", 0xC9: "sinh⁻¹(", 0xCA: "cosh(",
    0xCB: "cosh⁻¹(", 0xCC: "tanh(", 0xCD: "tanh⁻¹(", 0xCE: "If ", 0xCF: "Then", 0xD0: "Else", 0xD1: "While ",
    0xD2: "Repeat ", 0xD3: "For(", 0xD4: "End", 0xD5: "Return", 0xD6: "Lbl ", 0xD7: "Goto ", 0xD8: "Pause ",
    0xD9: "Stop", 0xDA: "IS>(", 0xDB: "DS<(", 0xDC: "Input ", 0xDD: "Prompt ", 0xDE: "Disp ", 0xDF: "DispGraph",
    0xE0: "Output(", 0xE1: "ClrHome", 0xE2: "Fill(", 0xE3: "SortA(", 0xE4: "SortD(", 0xE5: "DispTable",
    0xE6: "Menu(", 0xE7: "Send(", 0xE8: "Get(", 0xE9: "PlotsOn ", 0xEA: "PlotsOff ", 0xEB: "∟", 0xEC: "Plot1(",
    0xED: "Plot2(", 0xEE: "Plot3(", 0xF0: "^", 0xF1: "×√", 0xF2: "1-Var Stats ", 0xF3: "2-Var Stats ",
    0xF4: "LinReg(a+bx) ", 0xF5: "ExpReg ", 0xF6: "LnReg ", 0xF7: "PwrReg ", 0xF8: "Med-Med ", 0xF9: "QuadReg ",
    0xFA: "ClrList ", 0xFB: "ClrTable", 0xFC: "Histogram", 0xFD: "xyLine", 0xFE: "Scatter", 0xFF: "LinReg(ax+b) ",
}
_ONE.update({0x30 + digit: str(digit) for digit in range(10)})
_ONE.update({0x41 + index: chr(ord("A") + index) for index in range(26)})

_LOWER = {}
_code = 0xB0
for _letter in "abcdefghijklmnopqrstuvwxyz":
    if _code == 0xBB:          # BBBBh is not a letter
        _code += 1
    _LOWER[_code] = _letter
    _code += 1

_TWO = {
    0x5C: {index: f"[{chr(ord('A') + index)}]" for index in range(10)},
    0x5D: {index: f"L{index + 1}" for index in range(6)},
    0x5E: {**{0x10 + index: f"Y{(index + 1) % 10}" for index in range(10)},
           **{0x20 + 2 * index: f"X{index + 1}ᴛ" for index in range(6)},
           **{0x21 + 2 * index: f"Y{index + 1}ᴛ" for index in range(6)},
           **{0x40 + index: f"r{index + 1}" for index in range(6)}, 0x80: "u", 0x81: "v", 0x82: "w"},
    0x60: {index: f"Pic{(index + 1) % 10}" for index in range(10)},
    0x61: {index: f"GDB{(index + 1) % 10}" for index in range(10)},
    0xAA: {index: f"Str{(index + 1) % 10}" for index in range(10)},
    0xBB: {0x6A: "Asm(", 0x6B: "AsmComp(", 0x6C: "AsmPrgm", 0x6D: "[AsmCode]", 0xD7: "@", 0xD8: "#", 0xD9: "$",
           0xDA: "&", 0xDB: "`", 0xDC: ";", 0xDD: "\\", 0xDE: "|", 0xDF: "_", 0xE0: "%", 0xCF: "~", **_LOWER},
    0xEF: {0x00: "setDate(", 0x01: "setTime(", 0x02: "checkTmr(", 0x03: "setDtFmt(", 0x04: "setTmFmt(",
           0x05: "timeCnv(", 0x06: "dayOfWk(", 0x07: "getDtStr ", 0x08: "getTmStr ", 0x09: "getDate",
           0x0A: "getTime", 0x0B: "startTmr", 0x0C: "getDtFmt", 0x0D: "getTmFmt", 0x0E: "isClockOn",
           0x0F: "ClockOff", 0x10: "ClockOn", 0x11: "OpenLib(", 0x12: "ExecLib"},
}
PREFIXES = frozenset(_TWO) | {0x62, 0x63, 0x7E}


def detokenize(data: bytes) -> str:
    """The text of a tokenized program."""
    out = []
    index = 0
    while index < len(data):
        byte = data[index]
        if byte in PREFIXES and index + 1 < len(data):
            second = data[index + 1]
            out.append(_TWO.get(byte, {}).get(second, f"[{byte:02X}{second:02X}]"))
            index += 2
        else:
            out.append(_ONE.get(byte, f"[{byte:02X}]"))
            index += 1
    return "".join(out)


def tokens(data: bytes) -> list[str]:
    """The program's tokens, one string each."""
    found = []
    index = 0
    while index < len(data):
        byte = data[index]
        if byte in PREFIXES and index + 1 < len(data):
            found.append(_TWO.get(byte, {}).get(data[index + 1], f"[{byte:02X}{data[index + 1]:02X}]"))
            index += 2
        else:
            found.append(_ONE.get(byte, f"[{byte:02X}]"))
            index += 1
    return found
