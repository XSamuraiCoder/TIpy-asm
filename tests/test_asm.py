"""Assembly files imported with `from name import routine`.

Run with:  python -m unittest discover -s tests -v
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from asm_sim import run_program, variable

from ti84asm.cli import main
from ti84asm.compiler import Compiler
from ti84asm.errors import CompileError

TARGETS = ("ce", "classic")

# These instructions mean the same on the Z80 and the eZ80, so one file serves both.
FASTMATH = """\
; tipy: def add3(a, b, c)
add3:
    add hl,de
    add hl,bc
    ret

; tipy: def double(value)
double:
    add hl,hl
    ret

; tipy: def seven()
seven:
    ld hl,7
    ret
"""


class AsmTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, name: str, text: str) -> Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def run_both(self, source: str, name: str = "r") -> list[int]:
        results = []
        for target in TARGETS:
            sim, compiler = run_program(source, target, source_dir=self.folder)
            self.assertEqual(sim.exit_sp, sim.sp_start, target)
            results.append(variable(sim, compiler, name))
        return results

    def compile_error(self, source: str, target: str = "ce") -> str:
        with self.assertRaises(CompileError) as caught:
            Compiler("T", target, source_dir=self.folder).compile(source)
        return str(caught.exception)

    def test_arguments_go_in_hl_de_bc_and_the_result_comes_back_in_hl(self):
        self.write("fastmath.asm", FASTMATH)
        source = "from fastmath import add3, double, seven\nx = 5\nr = add3(1, x, double(x)) + seven() * 100\n"
        self.assertEqual(self.run_both(source), [716, 716])

    def test_keywords_aliases_star_import_and_use_inside_functions(self):
        self.write("fastmath.asm", FASTMATH)
        source = textwrap.dedent("""\
            from fastmath import add3 as total, double
            from fastmath import *
            def twice_sum(a, b):
                return double(total(a, c=b, b=0))
            r = twice_sum(2, 3) + seven()
            """)
        self.assertEqual(self.run_both(source), [17, 17])

    def test_routine_called_as_a_statement(self):
        self.write("io.s", "; tipy: def touch()\ntouch:\n    ret\n")
        self.assertEqual(self.run_both("from io import touch\ntouch()\nr = 1\n"), [1, 1])

    def test_target_specific_file_wins(self):
        self.write("pick.asm", "; tipy: def which()\nwhich:\n    ld hl,1\n    ret\n")
        self.write("pick.ce.asm", "; tipy: def which()\nwhich:\n    ld hl,2\n    ret\n")
        self.assertEqual(self.run_both("from pick import which\nr = which()\n"), [2, 1])

    def test_dotted_module_in_a_subfolder(self):
        self.write("lib/fastmath.asm", FASTMATH)
        self.assertEqual(self.run_both("from lib.fastmath import seven\nr = seven()\n"), [7, 7])

    def test_routine_is_emitted_once_after_the_program(self):
        self.write("fastmath.asm", FASTMATH)
        assembly = Compiler("T", "ce", source_dir=self.folder).compile(
            "from fastmath import seven\nfrom fastmath import double\nr = seven()\n")
        self.assertEqual(assembly.count("; Assembly from fastmath.asm"), 1)
        self.assertLess(assembly.index("program_exit:"), assembly.index("seven:"))

    def test_errors_explain_what_to_fix(self):
        self.write("fastmath.asm", FASTMATH)
        self.write("empty.asm", "nothing:\n    ret\n")
        self.write("nolabel.asm", "; tipy: def ghost()\n    ret\n")
        self.write("toomany.asm", "; tipy: def four(a, b, c, d)\nfour:\n    ret\n")
        self.write("clash.asm", "; tipy: def _rt_mul()\n_rt_mul:\n    ret\n")
        cases = [
            ("from missing import x\n", "expected missing.py, missing.asm, or missing.s"),
            ("from fastmath import cube\n", "does not declare cube"),
            ("from empty import nothing\n", "declares no routines"),
            ("from nolabel import ghost\n", "has no label"),
            ("from toomany import four\n", "at most 3 parameters"),
            ("from clash import _rt_mul\n", "clash"),
            ("from fastmath import seven\nr = seven(1)\n", "takes 0 argument"),
            ("from fastmath import add3\nr = add3(1, 2)\n", "missing argument"),
            ("from fastmath import seven\ndef seven():\n    return 1\n", "both a Python function"),
            ("if 1:\n    from fastmath import seven\n", "module scope"),
        ]
        for source, message in cases:
            with self.subTest(source=source):
                self.assertIn(message, self.compile_error(source))

    def test_flash_target_says_assembly_needs_an_assembly_target(self):
        from ti84asm.cgen import FlashAppCompiler

        with self.assertRaisesRegex(CompileError, "only on the ce and classic targets"):
            FlashAppCompiler("T").compile("from fastmath import seven\nr = seven()\n")

    def test_project_build_assembles_with_fasmg(self):
        self.write("pyproject.toml", '[tool.tipy]\nname = "ASM"\n')
        self.write("src/fastmath.asm", FASTMATH)
        self.write("src/main.py", "from fastmath import add3\nprint(add3(1, 2, 3))\n")
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.folder)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["build", "--target", "ce", "--keep-asm"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue((self.folder / "bin" / "ASM.8xp").is_file())
        self.assertIn("add3:", (self.folder / "bin" / "ASM.asm").read_text(encoding="ascii"))



class AsmExampleTests(unittest.TestCase):
    """examples/asm_demo: one shared file, plus a different screen routine per target."""

    def run_example(self, target):
        from ti84asm.project import load_sources

        main_file = Path(__file__).resolve().parent.parent / "examples" / "asm_demo" / "src" / "main.py"
        source, _ = load_sources(main_file)
        sim, _ = run_program(source, target, source_dir=main_file.parent, keys=[0, 9])
        self.assertEqual(sim.output, "Bits in 1234: 5\n1 + 2 + 3 = 6\n")
        return sim

    def test_ce_fills_video_ram_with_the_color(self):
        sim = self.run_example("ce")
        self.assertEqual((sim.vram(0, 0), sim.vram(319, 239)), (0x001F, 0x001F))

    def test_classic_fills_the_graph_buffer(self):
        sim = self.run_example("classic")
        self.assertEqual({sim.read(0x9340 + offset) for offset in range(768)}, {0xFF})

if __name__ == "__main__":
    unittest.main()
