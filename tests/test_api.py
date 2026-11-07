"""The API table, the compiler, the assembler, and the editor stubs must agree.

Run with:  python -m unittest discover -s tests -v
"""
import ast
import subprocess
import tempfile
import unittest
from pathlib import Path

from ti84asm.compiler import Compiler
from ti84asm.errors import CompileError
from ti84libs.api import API

STUBS = Path(__file__).resolve().parent.parent / "ti84"


def program(library: str, example: str) -> str:
    imports = sorted({library, "keyboard", "color"})
    lines = [f"from ti84 import {name}" for name in imports]
    return "\n".join((*lines, "x = 3", "y = 4", "z = 0", "score = 5", "hero = 0", example, ""))


def examples():
    for library, methods in API.items():
        for name, method in methods.items():
            if method.example:
                yield library, name, method


class ApiTableTests(unittest.TestCase):
    def test_every_example_compiles_on_its_targets(self):
        for library, name, method in examples():
            for target in method.targets:
                with self.subTest(library=library, method=name, target=target):
                    assembly = Compiler("T", target).compile(program(library, method.example))
                    self.assertNotIn("TODO", assembly)

    def test_every_ce_example_assembles_with_fasmg(self):
        from ti84asm.fasmg import ensure_ce_includes, ensure_fasmg

        root, fasmg = ensure_ce_includes(), ensure_fasmg()
        for library, name, method in examples():
            if "ce" not in method.targets:
                continue
            with self.subTest(library=library, method=name), tempfile.TemporaryDirectory() as folder:
                source, output = Path(folder) / "t.asm", Path(folder) / "t.8xp"
                source.write_text(Compiler("T", "ce").compile(program(library, method.example)), encoding="ascii")
                result = subprocess.run([fasmg, str(source), str(output)], cwd=root,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(output.is_file())

    def test_every_classic_example_assembles_with_spasm(self):
        from ti84asm.fasmg import ensure_classic_include_directory, find_classic_assembler

        spasm = find_classic_assembler()
        if spasm is None:
            self.skipTest("SPASM-ng is not on PATH")
        include = ensure_classic_include_directory(spasm)
        for library, name, method in examples():
            if "classic" not in method.targets:
                continue
            with self.subTest(library=library, method=name), tempfile.TemporaryDirectory() as folder:
                source, output = Path(folder) / "t.asm", Path(folder) / "T.8xp"
                source.write_text(Compiler("T", "classic").compile(program(library, method.example)), encoding="ascii")
                result = subprocess.run([spasm, "-I", str(include), str(source), str(output)], cwd=include,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(output.is_file())

    def test_methods_unavailable_on_a_target_say_so(self):
        for library, name, method in examples():
            for target in {"ce", "classic"} - set(method.targets):
                with self.subTest(library=library, method=name, target=target):
                    with self.assertRaisesRegex(CompileError, "not available on the"):
                        Compiler("T", target).compile(program(library, method.example))

    def test_stubs_declare_exactly_the_public_api(self):
        for library, methods in API.items():
            if library == "graph":
                continue
            tree = ast.parse((STUBS / f"{library}.pyi").read_text(encoding="utf-8"))
            declared = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            with self.subTest(library=library):
                self.assertTrue({name for name, method in methods.items() if method.targets} <= declared,
                                f"missing from the stub: {sorted(set(methods) - declared)}")
                from ti84libs.api import flash_available
                extra = {name for name in declared - set(methods) if not flash_available(library, name)}
                self.assertFalse(extra, f"stub declares methods nothing implements: {sorted(extra)}")


class ErrorMessageTests(unittest.TestCase):
    def error(self, source: str, target: str = "ce") -> str:
        with self.assertRaises(CompileError) as caught:
            Compiler("T", target).compile(source)
        return str(caught.exception)

    def test_misspelled_method_gets_a_suggestion(self):
        message = self.error("from ti84 import graphics\ngraphics.pixl(1, 2)\n")
        self.assertIn("line 2:", message)
        self.assertIn("did you mean graphics.pixel()", message)

    def test_missing_import_says_what_to_add(self):
        self.assertIn("from ti84 import graphics", self.error("graphics.clear()\n"))

    def test_misspelled_library_and_function_get_suggestions(self):
        self.assertIn("did you mean graphics", self.error("from ti84 import grafics\n"))
        self.assertIn("did you mean spin()", self.error("def spin():\n    pass\nspinn()\n"))

    def test_void_method_cannot_be_used_as_a_value(self):
        self.assertIn("does not return a value", self.error("from ti84 import graphics\nx = graphics.clear()\n"))

    def test_retired_and_flash_only_libraries_point_elsewhere(self):
        self.assertIn("ti84.storage", self.error("from ti84 import fileioc\n"))
        self.assertIn("flash-app", self.error("from ti84 import graph\n"))

    def test_font_methods_point_to_graphics_text(self):
        self.assertIn("graphics.text", self.error('from ti84 import font\nx = font.load("F")\n'))

    def test_unsupported_syntax_names_the_feature_and_line(self):
        message = self.error("x = 1\ny = x / 2\n")
        self.assertTrue(message.startswith("line 2:"), message)
        self.assertIn("true division", message)

    def test_undefined_variable_gets_a_suggestion(self):
        self.assertIn("did you mean 'score'", self.error("score = 1\nx = scor + 1\n"))


if __name__ == "__main__":
    unittest.main()
