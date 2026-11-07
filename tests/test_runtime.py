"""Run generated assembly in tests/asm_sim.py and compare it with CPython.

Run with:  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from asm_sim import run_program, variable

from ti84asm.compiler import Compiler
from ti84asm.errors import CompileError

TARGETS = ("ce", "classic")
SAMPLES = (0, 1, -1, 2, 7, -7, 13, -13, 100, -100, 255, 1000, -1000, 32767, -32768)


def wrap(value: int, target: str) -> int:
    bits = 24 if target == "ce" else 16
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def result(source: str, target: str, name: str = "r", **kwargs) -> int:
    sim, compiler = run_program(source, target, **kwargs)
    return variable(sim, compiler, name)


class ArithmeticTests(unittest.TestCase):
    def check_binary(self, symbol, function, right_samples=SAMPLES):
        for target in TARGETS:
            for left in SAMPLES:
                for right in right_samples:
                    source = f"a = {left}\nb = {right}\nr = a {symbol} b\n"
                    with self.subTest(target=target, left=left, op=symbol, right=right):
                        self.assertEqual(result(source, target), wrap(function(left, right), target))

    def test_add_sub_mul(self):
        self.check_binary("+", lambda a, b: a + b)
        self.check_binary("-", lambda a, b: a - b)
        self.check_binary("*", lambda a, b: a * b)

    def test_floor_division_and_modulo_match_python(self):
        nonzero = [value for value in SAMPLES if value and value != -32768]
        self.check_binary("//", lambda a, b: a // b, nonzero)
        self.check_binary("%", lambda a, b: a % b, nonzero)

    def test_division_by_zero_is_defined_at_runtime_and_rejected_when_literal(self):
        self.assertEqual(result("a = 5\nb = 0\nr = a // b\n", "ce"), 0)
        self.assertEqual(result("a = 5\nb = 0\nr = a % b\n", "ce"), 5)
        with self.assertRaisesRegex(CompileError, "division by zero"):
            Compiler("T", "ce").compile("a = 5\nr = a // 0\n")

    def test_bit_operations(self):
        self.check_binary("&", lambda a, b: a & b)
        self.check_binary("|", lambda a, b: a | b)
        self.check_binary("^", lambda a, b: a ^ b)
        self.check_binary("<<", lambda a, b: a << b, (0, 1, 3, 7))
        self.check_binary(">>", lambda a, b: a >> b, (0, 1, 3, 7, 15))

    def test_unary(self):
        for target in TARGETS:
            for value in SAMPLES:
                self.assertEqual(result(f"a = {value}\nr = ~a\n", target), wrap(~value, target))
                self.assertEqual(result(f"a = {value}\nr = -a\n", target), wrap(-value, target))
                self.assertEqual(result(f"a = {value}\nr = not a\n", target), int(not value))

    def test_comparisons_are_signed(self):
        for target in TARGETS:
            for left in SAMPLES:
                for right in SAMPLES:
                    for symbol, expected in (("<", left < right), ("<=", left <= right), (">", left > right),
                                             (">=", left >= right), ("==", left == right), ("!=", left != right)):
                        with self.subTest(target=target, left=left, op=symbol, right=right):
                            self.assertEqual(result(f"a = {left}\nb = {right}\nr = a {symbol} b\n", target), int(expected))

    def test_and_or_return_an_operand_like_python(self):
        for target in TARGETS:
            for left in (0, 5):
                for right in (0, 9):
                    self.assertEqual(result(f"a = {left}\nb = {right}\nr = a and b\n", target), left and right)
                    self.assertEqual(result(f"a = {left}\nb = {right}\nr = a or b\n", target), left or right)

    def test_conditional_expression_and_truthiness(self):
        for target in TARGETS:
            self.assertEqual(result("a = 3\nr = 10 if a else 20\n", target), 10)
            self.assertEqual(result("a = 0\nr = 10 if a else 20\n", target), 20)
            self.assertEqual(result("a = 0\nr = 1\nif not a and r:\n    r = 2\n", target), 2)
            self.assertEqual(result("a = 1\nb = 5\nc = 9\nr = 0\nif a < b < c:\n    r = 1\n", target), 1)

    def test_large_literal_keeps_its_bit_pattern(self):
        self.assertEqual(result("a = 0xABCD\nr = a & 0xFFFF\n", "ce"), 0xABCD)
        self.assertEqual(result("a = 0xABCD\nr = a & 0xFFFF\n", "classic"), wrap(0xABCD, "classic"))


class ControlFlowTests(unittest.TestCase):
    def test_runtime_range_bounds_are_evaluated_once(self):
        source = "n = 4\nr = 0\nfor i in range(n):\n    r += i\n    n = 0\n"
        for target in TARGETS:
            self.assertEqual(result(source, target), 6)

    def test_range_negative_step(self):
        for target in TARGETS:
            self.assertEqual(result("n = 5\nr = 0\nfor i in range(n, 0, -2):\n    r += i\n", target), 9)

    def test_break_and_continue(self):
        source = """
r = 0
for i in range(10):
    if i == 2:
        continue
    if i == 5:
        break
    r += i
j = 0
while True:
    j += 1
    if j > 3:
        break
r += j * 100
"""
        for target in TARGETS:
            self.assertEqual(result(source, target), 8 + 400)

    def test_exit_leaves_from_inside_a_function(self):
        source = "r = 1\ndef stop():\n    exit()\nstop()\nr = 2\n"
        for target in TARGETS:
            self.assertEqual(result(source, target), 1)


class FunctionTests(unittest.TestCase):
    def test_return_values_parameters_defaults_and_keywords(self):
        source = """
def add(a, b=10):
    return a + b
r = add(1) + add(1, 2) * 100 + add(b=3, a=4) * 1000
"""
        for target in TARGETS:
            self.assertEqual(result(source, target), wrap(11 + 300 + 7000, target))

    def test_locals_do_not_touch_globals_and_global_statement_does(self):
        source = """
x = 1
y = 1
def f():
    global y
    x = 50
    y = 60
    return x
r = f() + x * 1000 + y
"""
        for target in TARGETS:
            self.assertEqual(result(source, target), wrap(50 + 1000 + 60, target))

    def test_nested_calls_in_arguments(self):
        source = "def inc(a):\n    return a + 1\ndef two(a, b):\n    return a * 100 + b\nr = two(inc(inc(1)), inc(5))\n"
        for target in TARGETS:
            self.assertEqual(result(source, target), 306)

    def test_function_defined_after_its_call_like_a_main_guard(self):
        source = "r = 0\ndef main():\n    global r\n    r = later()\ndef later():\n    return 7\nif __name__ == '__main__':\n    main()\n"
        for target in TARGETS:
            self.assertEqual(result(source, target), 7)

    def test_stack_is_balanced_at_exit(self):
        source = "def f(a):\n    for i in range(3):\n        if i == 1:\n            return a * i\nr = f(f(2) + 1)\n"
        for target in TARGETS:
            sim, _ = run_program(source, target)
            self.assertEqual(sim.exit_sp, sim.sp_start)

    def test_recursion_is_rejected_with_the_cycle(self):
        with self.assertRaisesRegex(CompileError, r"recursion.*a -> b -> a"):
            Compiler("T", "ce").compile("def a():\n    b()\ndef b():\n    a()\n")

    def test_assigning_a_global_without_declaring_it_explains_why(self):
        with self.assertRaisesRegex(CompileError, r"global x"):
            Compiler("T", "ce").compile("x = 1\ndef f():\n    x += 1\n")


class ArrayTests(unittest.TestCase):
    def test_tuple_lookup_and_list_writes(self):
        source = """
TABLE = (10, -20, 30)
scores = [0] * 4
i = 1
r = TABLE[i]
scores[i] = 7
scores[2] = scores[i] + 1
scores[2] += 1
q = scores[2] + TABLE[-1]
"""
        for target in TARGETS:
            sim, compiler = run_program(source, target)
            self.assertEqual(variable(sim, compiler, "r"), -20)
            self.assertEqual(variable(sim, compiler, "q"), 39)

    def test_tuples_are_immutable_and_constant_bounds_are_checked(self):
        with self.assertRaisesRegex(CompileError, "tuple"):
            Compiler("T", "ce").compile("T = (1, 2)\nT[0] = 1\n")
        with self.assertRaisesRegex(CompileError, "out of range"):
            Compiler("T", "ce").compile("T = (1, 2)\nr = T[2]\n")

    def test_unpacking_and_chained_assignment(self):
        for target in TARGETS:
            sim, compiler = run_program("a, b = 1, 2\na, b = b, a\nc = d = a + 5\n", target)
            self.assertEqual([variable(sim, compiler, n) for n in "abcd"], [2, 1, 7, 7])


class NamedConstantTests(unittest.TestCase):
    def test_names_assigned_once_work_where_constants_are_required(self):
        source = """
SIZE = 3
STEP = SIZE - 1
items = [7] * SIZE
r = 0
for i in range(0, 6, STEP):
    r += 1
j = SIZE - 1
q = items[j]
"""
        for target in TARGETS:
            sim, compiler = run_program(source, target)
            self.assertEqual((variable(sim, compiler, "r"), variable(sim, compiler, "q")), (3, 7))

    def test_reassigned_and_shadowed_names_are_not_treated_as_constants(self):
        source = """
n = 2
n = n + 1
LIMIT = 5
def f(LIMIT):
    return LIMIT * 2
r = f(4) + n * 100
"""
        for target in TARGETS:
            self.assertEqual(result(source, target), 308)

    def test_global_written_in_a_function_is_not_constant(self):
        source = "x = 1\ndef f():\n    global x\n    x = 9\nf()\nr = x\n"
        for target in TARGETS:
            self.assertEqual(result(source, target), 9)

    def test_reading_before_assignment_is_still_an_error(self):
        with self.assertRaisesRegex(CompileError, "before assignment|not defined"):
            Compiler("T", "ce").compile("r = A\nA = 1\n")


class PrintTests(unittest.TestCase):
    def test_print_mixes_strings_and_integers(self):
        for target in TARGETS:
            sim, _ = run_program('a = -305\nprint("A", a, 0)\nprint(a + 5)\nprint("B")\n', target)
            self.assertEqual(sim.output, "A -305 0\n-300\nB\n")


class MathLibraryTests(unittest.TestCase):
    def test_every_helper(self):
        cases = [("math.abs(a)", abs), ("math.sign(a)", lambda a: (a > 0) - (a < 0)),
                 ("abs(a)", abs), ("max(a, 3, 1)", lambda a: max(a, 3, 1)), ("min(a, 3)", lambda a: min(a, 3)),
                 ("math.clamp(a, -5, 9)", lambda a: max(min(a, 9), -5)),
                 ("math.min(a, 2)", lambda a: min(a, 2)), ("math.max(a, 2)", lambda a: max(a, 2))]
        for target in TARGETS:
            for text, function in cases:
                for value in SAMPLES:
                    with self.subTest(target=target, call=text, value=value):
                        source = f"from ti84 import math\na = {value}\nr = {text}\n"
                        self.assertEqual(result(source, target), wrap(function(value), target))

    def test_sqrt(self):
        import math
        for target in TARGETS:
            for value in (0, 1, 2, 3, 4, 15, 16, 17, 255, 10000, 32767):
                self.assertEqual(result(f"from ti84 import math\na = {value}\nr = math.sqrt(a)\n", target), math.isqrt(value))
            self.assertEqual(result("from ti84 import math\na = -4\nr = math.sqrt(a)\n", target), 0)

    def test_pow_sin_cos(self):
        for target in TARGETS:
            self.assertEqual(result("from ti84 import math\na = 3\nr = math.pow(a, 4)\n", target), 81)
            for degrees, sine in ((0, 0), (30, 128), (90, 256), (150, 128), (180, 0), (210, -128), (270, -256), (-90, -256)):
                self.assertEqual(result(f"from ti84 import math\na = {degrees}\nr = math.sin(a)\n", target), sine)
            self.assertEqual(result("from ti84 import math\na = 60\nr = math.cos(a)\n", target), 128)


class RandomTests(unittest.TestCase):
    def test_values_stay_in_range_and_vary(self):
        source = """
from ti84 import random
random.seed(1234)
low = 100
high = -100
for i in range(200):
    v = random.randint(-3, 3)
    low = min(low, v)
    high = max(high, v)
"""
        for target in TARGETS:
            sim, compiler = run_program(source, target)
            self.assertEqual((variable(sim, compiler, "low"), variable(sim, compiler, "high")), (-3, 3))


class KeyboardTests(unittest.TestCase):
    def test_read_returns_a_clean_value_on_both_targets(self):
        source = "from ti84 import keyboard\nr = 0\nk = keyboard.read()\nif k == keyboard.ENTER:\n    r = 1\n"
        for target in TARGETS:
            self.assertEqual(result(source, target, keys=[0, 9]), 1)

    def test_get_does_not_block(self):
        source = "from ti84 import keyboard\nr = keyboard.get()\n"
        for target in TARGETS:
            self.assertEqual(result(source, target), 0)
            self.assertEqual(result(source, target, keys=[15]), 15)

    def test_is_down_reads_the_held_key_only(self):
        source = "from ti84 import keyboard\nu = keyboard.is_down(keyboard.UP)\nd = keyboard.is_down(keyboard.DOWN)\ne = keyboard.is_down(keyboard.DEL)\n"
        for target in TARGETS:
            sim, compiler = run_program(source, target, held={4, 0x38})
            self.assertEqual([variable(sim, compiler, n) for n in "ude"], [1, 0, 1])


class StorageTests(unittest.TestCase):
    def test_round_trip_and_first_byte_is_offset_zero(self):
        source = """
from ti84 import storage
storage.create("SAVE", 4)
i = 3
storage.write_byte("SAVE", 0, 11)
storage.write_byte("SAVE", i, 44)
a = storage.read_byte("SAVE", 0)
b = storage.read_byte("SAVE", i)
s = storage.size("SAVE")
e = storage.exists("SAVE")
m = storage.exists("NOPE")
"""
        for target in TARGETS:
            sim, compiler = run_program(source, target)
            self.assertEqual(sim.appvar("SAVE"), bytes([11, 0, 0, 44]))
            self.assertEqual([variable(sim, compiler, n) for n in "absem"], [11, 44, 4, 1, 0])

    def test_create_keeps_existing_data_and_delete_removes(self):
        source = 'from ti84 import storage\nstorage.create("SAVE", 2)\na = storage.read_byte("SAVE", 1)\nstorage.delete("SAVE")\nb = storage.exists("SAVE")\nstorage.delete("SAVE")\n'
        for target in TARGETS:
            sim, compiler = run_program(source, target, appvars={"SAVE": b"\x05\x06"})
            self.assertEqual([variable(sim, compiler, "a"), variable(sim, compiler, "b")], [6, 0])

    def test_out_of_range_offset_ends_the_program_cleanly(self):
        source = 'from ti84 import storage\nr = 1\ndef f():\n    global r\n    r = storage.read_byte("SAVE", 2)\nf()\nr = 9\n'
        for target in TARGETS:
            sim, compiler = run_program(source, target, appvars={"SAVE": b"\x05\x06"})
            self.assertEqual(variable(sim, compiler, "r"), 1)
            self.assertEqual(sim.sp, sim.sp_start + sim.word_bytes)

    def test_file_library_u16_and_clear(self):
        source = 'from ti84 import file\nfile.create("D", 4)\nfile.write_u16("D", 1, 513)\nr = file.read_u16("D", 1)\nq = file.read_byte("D", 2)\nfile.clear("D")\ns = file.read_u16("D", 1)\n'
        for target in TARGETS:
            sim, compiler = run_program(source, target)
            self.assertEqual([variable(sim, compiler, n) for n in "rqs"], [513, 2, 0])


class DrawingTests(unittest.TestCase):
    """Runtime arguments must draw exactly what the literal lowering draws."""

    def same_pixels(self, call: str, runtime: str, target: str, setup: str = "x = 3\ny = 4\n"):
        head = f"from ti84 import graphics\n{setup}"
        literal, _ = run_program(head + call + "\n", target)
        dynamic, _ = run_program(head + runtime + "\n", target)
        self.assertEqual(dynamic.lit_pixels(), literal.lit_pixels(), call)
        self.assertTrue(literal.lit_pixels(), call)

    def test_runtime_shapes_match_literal_shapes(self):
        shapes = [("graphics.pixel(3, 4, 1)", "graphics.pixel(x, y, 1)"),
                  ("graphics.line(3, 4, 20, 9, 1)", "graphics.line(x, y, 20, 9, 1)"),
                  ("graphics.line(20, 30, 3, 4, 1)", "graphics.line(20, 30, x, y, 1)"),
                  ("graphics.rect(3, 4, 10, 6, 1)", "graphics.rect(x, y, 10, 6, 1)"),
                  ("graphics.fill_rect(3, 4, 10, 6, 1)", "graphics.fill_rect(x, y, 10, 6, 1)"),
                  ("graphics.horiz_line(3, 4, 9, 1)", "graphics.horiz_line(x, y, 9, 1)"),
                  ("graphics.vert_line(3, 4, 9, 1)", "graphics.vert_line(x, y, 9, 1)"),
                  ("graphics.circle(20, 20, 7, 1)", "graphics.circle(x + 17, y + 16, 7, 1)"),
                  ("graphics.triangle(3, 4, 20, 8, 7, 25, 1)", "graphics.triangle(x, y, 20, 8, 7, 25, 1)")]
        for target in TARGETS:
            for literal, runtime in shapes:
                with self.subTest(target=target, call=literal):
                    self.same_pixels(literal, runtime, target)

    def test_runtime_fill_rect_clips_at_every_edge(self):
        source = "from ti84 import graphics\na = -2\nb = {b}\ngraphics.fill_rect(a, b, 5, 4, 1)\n"
        for target, (width, height) in (("ce", (320, 240)), ("classic", (96, 64))):
            sim, _ = run_program(source.format(b=height - 2), target)
            self.assertEqual(sim.lit_pixels(), {(x, y) for x in range(3) for y in (height - 2, height - 1)})

    def test_off_screen_runtime_pixel_is_ignored(self):
        source = "from ti84 import graphics\nx = -1\ny = 500\ngraphics.pixel(x, 0, 1)\ngraphics.pixel(0, y, 1)\n"
        for target in TARGETS:
            self.assertEqual(run_program(source, target)[0].lit_pixels(), set())

    def test_runtime_color_and_keyword_color(self):
        sim, _ = run_program("from ti84 import graphics\nc = 0xF800\ngraphics.pixel(1, 1, color=c)\ngraphics.fill_rect(2, 2, 1, 1, c)\nr = graphics.get_pixel(2, 2)\n", "ce")
        self.assertEqual(sim.vram(1, 1), 0xF800)
        self.assertEqual(sim.vram(2, 2), 0xF800)
        self.assertEqual(variable(sim, sim.compiler, "r"), 0xF800)

    def test_fill_screen_and_fill_circle(self):
        sim, _ = run_program("from ti84 import graphics\nc = 7\ngraphics.fill_screen(c)\n", "ce")
        self.assertEqual((sim.vram(0, 0), sim.vram(319, 239)), (7, 7))
        sim, _ = run_program("from ti84 import graphics\ngraphics.fill_circle(10, 10, 3, 1)\n", "ce")
        outline, _ = run_program("from ti84 import graphics\ngraphics.circle(10, 10, 3, 1)\n", "ce")
        # Rows from the center out are 7, 7, 5, and 3 pixels wide.
        self.assertEqual(len(sim.lit_pixels()), 7 + 2 * (7 + 5 + 3))
        self.assertTrue(outline.lit_pixels() <= sim.lit_pixels())

    def test_constant_colors_on_classic_are_mono(self):
        sim, _ = run_program("from ti84 import graphics, color\ngraphics.pixel(1, 1, graphics.RED)\ngraphics.pixel(2, 1, color.BLACK)\ngraphics.pixel(3, 1, color.WHITE)\n", "classic")
        self.assertEqual({point: value for point, value in sim.pixels.items()}, {(1, 1): 1, (2, 1): 1, (3, 1): 0})

    def test_text_int_draws_decimal_text(self):
        sim, _ = run_program("from ti84 import graphics\ns = -42\ngraphics.text_int(s, 5, 6)\n", "ce")
        self.assertEqual(sim.texts, [("-42", 5, 6)])


class SpriteTests(unittest.TestCase):
    PIXELS = bytes([2, 0, 2, 0, 0x34, 0x12, 0, 0, 0xFF, 0xFF, 0x01, 0x00])

    def test_load_draw_transparency_and_size(self):
        source = 'from ti84 import sprite\ns = sprite.load("HERO")\nx = 10\nsprite.draw(s, x, 20)\nw = sprite.width(s)\nh = sprite.height(s)\n'
        sim, compiler = run_program(source, "ce", appvars={"HERO": self.PIXELS})
        self.assertEqual((sim.vram(10, 20), sim.vram(11, 20), sim.vram(10, 21), sim.vram(11, 21)), (0x1234, 0, 0xFFFF, 1))
        self.assertEqual((variable(sim, compiler, "w"), variable(sim, compiler, "h")), (2, 2))

    def test_reading_an_archived_sprite(self):
        compiler = Compiler("T", "ce")
        from asm_sim import Sim
        source = 'from ti84 import sprite\ns = sprite.load("HERO")\nsprite.draw(s, 1, 1)\n'
        sim = Sim(compiler.compile(source), "ce", appvars={"HERO": self.PIXELS})
        sim.archive("HERO")
        sim.run()
        self.assertEqual(sim.vram(1, 1), 0x1234)

    def test_clipping_and_missing_sprite(self):
        source = 'from ti84 import sprite\ns = sprite.load("HERO")\na = -1\nsprite.draw(s, a, a)\nb = 319\nsprite.draw(s, b, 239)\nm = sprite.load("NONE")\nsprite.draw(m, 5, 5)\n'
        sim, compiler = run_program(source, "ce", appvars={"HERO": self.PIXELS})
        self.assertEqual(sim.vram(0, 0), 1)
        self.assertEqual(sim.vram(319, 239), 0x1234)
        self.assertEqual(variable(sim, compiler, "m"), 0)
        self.assertEqual(sim.vram(5, 5), 0)


class ColorTests(unittest.TestCase):
    def test_constant_and_runtime_results_agree(self):
        for text, args in (("color.from_rgb({0}, {1}, {2})", (255, 128, 16)), ("color.invert({0})", (0xF800,)),
                           ("color.to_grayscale({0})", (0x07E0,)), ("color.to_mono({0})", (0xFFFF,)),
                           ("color.to_mono({0})", (0,)), ("color.from_mono({0})", (0,)), ("color.from_mono({0})", (1,))):
            literal = text.format(*args)
            names = "abc"[:len(args)]
            runtime = text.format(*names)
            setup = "".join(f"{name} = {value}\n" for name, value in zip(names, args))
            constant = result(f"from ti84 import color\nr = {literal}\n", "ce")
            computed = result(f"from ti84 import color\n{setup}r = {runtime}\n", "ce")
            if "grayscale" in text:
                self.assertAlmostEqual(constant, computed, delta=0x0841 * 2, msg=literal)
            else:
                self.assertEqual(constant, computed, literal)

    def test_constants(self):
        self.assertEqual(result("from ti84 import color\nr = color.RED\n", "ce"), 0xF800)
        self.assertEqual(result("from ti84 import color\nr = color.WHITE\n", "classic"), 0)
        self.assertEqual(result("from ti84 import font\nr = font.BLUE\n", "ce"), 0x1F)

    def test_mono_convention_matches_the_classic_screen(self):
        self.assertEqual(result("from ti84 import color\nr = color.from_rgb(255, 255, 255)\n", "classic"), 0)
        self.assertEqual(result("from ti84 import color\nr = color.from_rgb(0, 0, 0)\n", "classic"), 1)


if __name__ == "__main__":
    unittest.main()
