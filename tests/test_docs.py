"""The documentation must cover the whole API and build without warnings.

Run with:  python -m unittest discover -s tests -v
"""
import importlib.util
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from ti84asm.compiler import Compiler
from ti84asm.errors import CompileError
from ti84libs.api import API, flash_available

DOCS = Path(__file__).resolve().parent.parent / "docs"


class CoverageTests(unittest.TestCase):
    def test_every_library_has_a_page_in_the_table_of_contents(self):
        index = (DOCS / "index.rst").read_text(encoding="utf-8")
        for library in API:
            with self.subTest(library=library):
                self.assertTrue((DOCS / "libraries" / f"{library}.rst").is_file())
                self.assertIn(f"libraries/{library}", index)

    def test_every_library_with_methods_generates_them(self):
        for library, methods in API.items():
            if methods:
                page = (DOCS / "libraries" / f"{library}.rst").read_text(encoding="utf-8")
                self.assertIn(f".. tipy-methods:: {library}", page)

    def test_every_listed_method_works_somewhere(self):
        for library, methods in API.items():
            for name, method in methods.items():
                with self.subTest(library=library, method=name):
                    self.assertTrue(method.targets or flash_available(library, name))


class SnippetTests(unittest.TestCase):
    """Every Python example in the docs must compile, apart from names it leaves undefined."""

    def compile_snippet(self, code: str) -> None:
        for _ in range(20):
            try:
                Compiler("T", "ce").compile(code)
                return
            except CompileError as exc:
                match = re.search(r"variable '(\w+)' (?:is not defined|may be read)", str(exc))
                if not match:
                    raise
                # Fragments use names like x and score that a real program would define.
                code = f"{match.group(1)} = 1\n{code}"
        self.fail("too many undefined names")

    def test_python_snippets_compile(self):
        checked = 0
        for page in DOCS.rglob("*.rst"):
            if "_build" in page.parts:
                continue
            for snippet in re.findall(r"code-block:: python\n\n((?:(?:   .*)?\n)+)", page.read_text(encoding="utf-8")):
                code = textwrap.dedent(snippet)
                with self.subTest(page=page.name, code=code):
                    # Skip a converter sample and an import of files only a real project has.
                    if "TODO(convert)" not in code and "from settings" not in code:
                        self.compile_snippet(code)
                        checked += 1
        self.assertGreater(checked, 10)


@unittest.skipUnless(importlib.util.find_spec("sphinx"), "Sphinx is not installed")
class BuildTests(unittest.TestCase):
    def test_build_has_no_warnings_and_documents_every_method(self):
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run([sys.executable, "-m", "sphinx", "-W", "--keep-going", "-q", "-b", "html",
                                     str(DOCS), output], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for library, methods in API.items():
                page = (Path(output) / "libraries" / f"{library}.html").read_text(encoding="utf-8")
                for name in methods:
                    self.assertIn(f'id="ti84.{library}.{name}"', page, f"{library}.{name}")


if __name__ == "__main__":
    unittest.main()
