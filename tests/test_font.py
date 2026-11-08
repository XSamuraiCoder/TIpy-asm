"""ti84.font draws exactly what the converter (convfont, and the font asset kind) writes.

Run with:  python -m unittest discover -s tests -v
"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from asm_sim import Sim

from ti84asm.compiler import Compiler
from ti84asm.convfont import Font, byte_columns, serialize_fontpack

WHITE, RED = 0xFFFF, 0xF800


def random_font(rng: random.Random, first: int, widths: list[int], height: int, above=0, below=0) -> Font:
    bitmaps = [bytes(rng.randrange(256) for _ in range(byte_columns(w) * height)) for w in widths]
    return Font(height, first, widths, bitmaps, space_above=above, space_below=below)


def pixel_set(font: Font, glyph: int, x: int, y: int) -> bool:
    columns = byte_columns(font.widths[glyph])
    return bool(font.bitmaps[glyph][y * columns + x // 8] & (0x80 >> (x % 8)))


class FontTests(unittest.TestCase):
    def run_program(self, source: str, pack: bytes) -> tuple[Sim, Compiler]:
        compiler = Compiler("T", "ce")
        sim = Sim(compiler.compile(source), "ce", appvars={"FONTS": pack})
        sim.run(30_000_000)
        return sim, compiler

    def value(self, sim, compiler, name):
        return sim.word(compiler.variables[name])

    def test_glyphs_draw_pixel_for_pixel(self):
        rng = random.Random(84)
        # Widths across byte boundaries; the second font is the one drawn.
        small = random_font(rng, 32, [3, 5], 4)
        big = random_font(rng, 65, [5, 8, 9, 13, 17], 11, above=2, below=1)
        pack = serialize_fontpack([small, big])
        source = ("from ti84 import font, graphics\n"
                  "f = font.load('FONTS', 1)\n"
                  "x = 4\n"
                  "for code in range(65, 70):\n"
                  "    x += font.char(f, code, x, 10, graphics.RED) + 1\n"
                  "h = font.height(f)\nw = font.width(f, 68)\nn = font.count('FONTS')\n"
                  "missing = font.width(f, 32)\nnone = font.load('FONTS', 2)\n")
        sim, compiler = self.run_program(source, pack)
        values = {name: self.value(sim, compiler, name) for name in ("h", "w", "n", "missing", "none", "x")}
        self.assertEqual(values, {"h": 14, "w": 13, "n": 2, "missing": 0, "none": 0,
                                  "x": 4 + sum(big.widths) + 5})
        left = 4
        for glyph, width in enumerate(big.widths):
            for y in range(big.height):
                for x in range(width):
                    expected = RED if pixel_set(big, glyph, x, y) else 0
                    got = sim.vram(left + x, 10 + 2 + y)
                    self.assertEqual(got if got == RED else 0, expected, (glyph, x, y))
            left += width + 1

    def test_a_missing_or_wrong_appvar_is_zero(self):
        source = "from ti84 import font\na = font.load('NOPE')\nb = font.count('FONTS')\nc = font.char(0, 65, 1, 1)\n"
        sim, compiler = self.run_program(source, b"NOTAPACK" + bytes(8))
        self.assertEqual([self.value(sim, compiler, n) for n in "abc"], [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
