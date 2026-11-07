"""The command line and project workflow, run the way a user runs them.

Run with:  python -m unittest discover -s tests -v
"""
import contextlib
import io
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from ti84asm.cli import main
from ti84asm.project import load_project
from ti84asm.errors import CompileError
from ti84asm.project_convert import cedev_to_python, ice_to_python

REPO = Path(__file__).resolve().parent.parent


def run(*arguments: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(arguments))
    return code, out.getvalue(), err.getvalue()


class Workspace(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.root)

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def project(self, table: str = 'name = "GAME"', main_text: str = "x = 1\n") -> None:
        self.write("pyproject.toml", f"[tool.tipy]\n{table}\n")
        self.write("src/main.py", main_text)


class NewProjectTests(Workspace):
    def test_new_project_checks_on_every_target(self):
        code, out, _ = run("new", "my-game")
        self.assertEqual(code, 0, out)
        self.assertEqual(load_project(self.root / "my-game").name, "MYGAME")
        code, out, err = run("check", "my-game", "--target", "both")
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("ce: ok", out)
        self.assertIn("classic: ok", out)

    def test_new_project_builds(self):
        run("new", "mygame")
        code, out, err = run("build", "mygame")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "mygame/bin/MYGAME.8xp").is_file())
        self.assertIn("bytes)", out)

    def test_new_refuses_to_overwrite(self):
        run("new", "mygame")
        (self.root / "mygame/src/main.py").write_text("keep = 1\n", encoding="utf-8")
        code, _, err = run("new", "mygame")
        self.assertEqual(code, 1)
        self.assertIn("not overwriting", err)
        self.assertEqual((self.root / "mygame/src/main.py").read_text(encoding="utf-8"), "keep = 1\n")

    def test_new_rejects_a_bad_name(self):
        code, _, err = run("new", "x", "--name", "much_too_long_name")
        self.assertEqual(code, 1)
        self.assertIn("program name", err)


class ProjectConfigTests(Workspace):
    def test_commands_find_the_project_from_a_subfolder(self):
        self.project()
        os.chdir(self.root / "src")
        code, out, err = run("compile")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "bin/GAME.asm").is_file(), out)

    def test_unrelated_parent_pyproject_is_skipped(self):
        self.write("pyproject.toml", '[project]\nname = "other"\n')
        self.write("inner/pyproject.toml", '[tool.tipy]\nname = "IN"\n')
        self.write("inner/src/main.py", "x = 1\n")
        os.chdir(self.root / "inner/src")
        self.assertEqual(load_project(Path.cwd()).name, "IN")

    def test_no_project_tells_you_how_to_make_one(self):
        code, _, err = run("build")
        self.assertEqual(code, 1)
        self.assertIn("tipy-asm new", err)

    def test_invalid_explicit_name_is_an_error_not_silently_changed(self):
        self.project('name = "my-long_program_name"')
        code, _, err = run("compile")
        self.assertEqual(code, 1)
        self.assertIn("1-8 ASCII letters", err)

    def test_project_name_is_derived_when_not_set(self):
        self.write("pyproject.toml", '[project]\nname = "my-long_program_name"\n\n[tool.tipy]\n')
        self.write("src/main.py", "x = 1\n")
        self.assertEqual(load_project(self.root).name, "mylongpr")

    def test_unknown_keys_are_listed_with_the_allowed_ones(self):
        self.project('name = "G"\ntargett = "ce"')
        code, _, err = run("compile")
        self.assertEqual(code, 1)
        self.assertIn("targett", err)
        self.assertIn("allowed:", err)

    def test_clean_removes_only_bindir(self):
        self.project()
        run("compile")
        code, out, _ = run("clean")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "bin").exists())
        self.assertTrue((self.root / "src/main.py").exists())
        self.assertEqual(run("clean")[1].strip(), "Nothing to clean")

    def test_dotted_project_imports(self):
        self.project(main_text="from game.player import speed\nr = speed(2)\n")
        self.write("src/game/player.py", "def speed(n):\n    return n * 3\n")
        self.assertEqual(run("check", "--target", "ce")[0], 0)


class DiagnosticTests(Workspace):
    def test_errors_point_at_the_original_file_and_line(self):
        self.project(main_text="from helper import f\nx = f()\n")
        helper = self.write("src/helper.py", '''\
            from ti84 import graphics
            def f():
                graphics.pixl(1, 2)
                return 1
            ''')
        code, _, err = run("check", "--target", "ce")
        self.assertEqual(code, 1)
        self.assertIn(f"{helper}:3: error:", err)
        self.assertIn("did you mean graphics.pixel()", err)
        self.assertIn("graphics.pixl(1, 2)", err)

    def test_check_reports_each_target_separately(self):
        self.project(main_text="from ti84 import sprite\nx = sprite.load('A')\n")
        code, out, err = run("check", "--target", "both")
        self.assertEqual(code, 1)
        self.assertIn("ce: ok", out)
        self.assertIn("classic: failed", err)

    def test_flash_target_is_checked(self):
        self.project(main_text="from ti84 import graph\n")
        self.assertEqual(run("check", "--target", "flash")[0], 0)
        self.assertEqual(run("check", "--target", "ce")[0], 1)

    def test_missing_source_file_is_a_clean_error(self):
        code, _, err = run("compile", "nothing.py")
        self.assertEqual(code, 1)
        self.assertIn("nothing.py", err)
        self.assertNotIn("Traceback", err)


class AssetTests(Workspace):
    def setUp(self):
        super().setUp()
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        image = Image.new("RGBA", (2, 1))
        image.putpixel((0, 0), (0, 0, 0, 255))
        image.putpixel((1, 0), (0, 0, 0, 0))
        (self.root / "assets").mkdir()
        image.save(self.root / "assets/hero.png")
        self.project('name = "G"\n\n[[tool.tipy.assets]]\nsource = "assets/hero.png"',
                     "from ti84 import sprite\ns = sprite.load('HERO')\n")

    def test_sprite_asset_format_keeps_black_visible(self):
        from ti84asm.project import build_assets

        config = load_project(self.root)
        self.assertEqual(config.assets[0].name, "HERO")
        written, unchanged = build_assets(config)
        self.assertEqual((len(written), unchanged), (1, []))
        data = written[0].read_bytes()
        # width 2, height 1, opaque black kept visible, then transparent 0.
        self.assertIn(bytes([2, 0, 1, 0, 0x20, 0, 0, 0]), data)

    def test_assets_only_rebuild_when_out_of_date(self):
        from ti84asm.project import build_assets

        config = load_project(self.root)
        build_assets(config)
        written, unchanged = build_assets(config)
        self.assertEqual((written, len(unchanged)), ([], 1))
        self.assertEqual(len(build_assets(config, force=True)[0]), 1)

    def test_bad_asset_config_is_reported(self):
        self.write("pyproject.toml", '[tool.tipy]\nname = "G"\n\n[[tool.tipy.assets]]\nname = "A"\n')
        with self.assertRaisesRegex(CompileError, "needs a source"):
            load_project(self.root)


class ToolCommandTests(Workspace):
    def test_doctor_reports_without_a_project(self):
        code, out, _ = run("doctor")
        self.assertEqual(code, 0)
        self.assertIn("fasmg", out)
        self.assertIn("tipy-asm new", out)

    def test_api_lists_libraries_and_methods(self):
        self.assertIn("graphics", run("api")[1])
        out = run("api", "keyboard")[1]
        self.assertIn("is_down(key)", out)
        self.assertIn("targets: ce, classic, flash", out)
        self.assertEqual(run("api", "nope")[0], 1)

    def test_version(self):
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()) as out:
            main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("tipy-asm", out.getvalue())

    def test_flash_app_without_a_project_dir_says_how_to_set_it(self):
        self.project()
        code, _, err = run("flash-app")
        self.assertEqual(code, 1)
        self.assertIn("project_dir", err)

    def test_flash_settings_load(self):
        self.project('name = "G"\n\n[tool.tipy.flash]\nproject_dir = "flash"\noptimize = "size"')
        config = load_project(self.root)
        self.assertEqual((config.flash.project_dir, config.flash.optimize), (self.root / "flash", "size"))


class ProgramTests(Workspace):
    """Run whole programs: the example game and the template from `tipy-asm new`."""

    def play(self, main_file: Path, target: str, **kwargs):
        import sys
        sys.path.insert(0, str(REPO / "tests"))
        from asm_sim import run_program
        from ti84asm.project import load_sources
        source, _ = load_sources(main_file)
        return run_program(source, target, **kwargs)[0]

    def test_example_game_runs_and_saves_on_both_targets(self):
        for target in ("ce", "classic"):
            with self.subTest(target=target):
                sim = self.play(REPO / "examples/catch/src/main.py", target, held={0x0F})
                self.assertEqual(sim.output, "Score: 0\nBest: 0\n")
                self.assertEqual(sim.appvar("CATCHSAV"), b"\0")

    def test_example_game_keeps_a_previous_high_score(self):
        sim = self.play(REPO / "examples/catch/src/main.py", "ce", held={0x0F}, appvars={"CATCHSAV": b"\x07"})
        self.assertEqual(sim.output, "Score: 0\nBest: 7\n")

    def test_screen_size_constants_work_on_the_flash_backend(self):
        self.write("size.py", "from ti84 import graphics\nx = graphics.width + graphics.height\n")
        self.assertEqual(run("check", "size.py", "--target", "flash")[0], 0)

    def test_new_project_template_draws_and_quits(self):
        run("new", "mygame")
        for target in ("ce", "classic"):
            with self.subTest(target=target):
                sim = self.play(self.root / "mygame/src/main.py", target, held={0x0F})
                self.assertEqual(sim.sp, sim.sp_start + sim.word_bytes)
        ce = self.play(self.root / "mygame/src/main.py", "ce", held={0x0F})
        self.assertEqual(ce.vram(160, 120), 0x001F)


class BundledToolchainTests(Workspace):
    def test_every_platform_binary_and_the_license_ship_in_the_package(self):
        toolchain = REPO / "ti84asm/toolchain"
        magic = {"fasmg.exe": b"MZ", "fasmg.x64": b"\x7fELF", "fasmg": b"\x7fELF"}
        for name, start in magic.items():
            self.assertEqual((toolchain / "bin" / name).read_bytes()[:len(start)], start, name)
        self.assertIn("Tomasz Grysztar", (toolchain / "fasmg-license.txt").read_text(encoding="utf-8"))

    def test_this_computer_uses_the_bundled_assembler_ignoring_path(self):
        from unittest import mock

        from ti84asm.fasmg import bundled_fasmg, ensure_fasmg
        if bundled_fasmg() is None:
            self.skipTest("no bundled fasmg for this computer")
        with mock.patch("shutil.which", return_value="/elsewhere/fasmg"):
            self.assertEqual(Path(ensure_fasmg()).parent, REPO / "ti84asm/toolchain/bin")

    def test_platforms_map_to_the_right_binary(self):
        from unittest import mock

        from ti84asm import fasmg
        for system, machine, expected in (("win32", "AMD64", "fasmg.exe"), ("win32", "ARM64", "fasmg.exe"),
                                          ("linux", "x86_64", "fasmg.x64"), ("linux", "i686", "fasmg"),
                                          ("linux", "aarch64", None), ("darwin", "arm64", None)):
            with mock.patch.object(fasmg.sys, "platform", system), mock.patch.object(fasmg.platform, "machine", return_value=machine):
                found = fasmg.bundled_fasmg()
                self.assertEqual(found.name if found else None, expected, (system, machine))

    def test_unsupported_computer_falls_back_to_path_then_explains(self):
        from unittest import mock

        from ti84asm import fasmg
        with mock.patch.object(fasmg, "bundled_fasmg", return_value=None):
            with mock.patch.object(fasmg.shutil, "which", return_value="/usr/local/bin/fasmg"):
                self.assertEqual(fasmg.ensure_fasmg(), "/usr/local/bin/fasmg")
            with mock.patch.object(fasmg.shutil, "which", return_value=None):
                with self.assertRaisesRegex(OSError, "--ce-assembler"):
                    fasmg.ensure_fasmg()


class FlashBackendTests(Workspace):
    def compile(self, source: str) -> str:
        from ti84asm.cgen import FlashAppCompiler
        return FlashAppCompiler("T").compile(source)

    def test_list_size_can_be_a_name_assigned_once(self):
        code = self.compile("N = 2\nSIZE = N + 1\na = [0] * SIZE\ndef f(i):\n    a[i] = 1\nf(0)\n")
        self.assertIn("ti84py_arr_0[3]", code)

    def test_reassigned_or_written_names_are_not_list_sizes(self):
        for source in ("n = 3\nn = 4\na = [0] * n\nb = a[0]\n",
                       "n = 3\ndef g():\n    global n\n    n = 4\ng()\na = [0] * n\nb = a[0]\n"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(CompileError, "list size must be a constant"):
                    self.compile(source)

    def test_a_local_shadowing_a_constant_is_not_a_list_size(self):
        source = "N = 3\ndef f(N):\n    a = [0] * N\n    return a[0]\nf(1)\n"
        with self.assertRaisesRegex(CompileError, "list size must be a constant"):
            self.compile(source)

    def test_real_cause_replaces_undefined_name(self):
        source = "n = int(2)\nn = 3\na = [0] * n\ndef f(i):\n    a[i] = 1\nf(0)\n"
        with self.assertRaises(CompileError) as caught:
            self.compile(source)
        self.assertNotIn("is not defined", str(caught.exception))
        self.assertIn("line 3:", str(caught.exception))
        self.assertIn("list size must be a constant", str(caught.exception))

    def test_truly_undefined_name_is_still_reported(self):
        with self.assertRaisesRegex(CompileError, "'missing' is not defined"):
            self.compile("def f():\n    return missing\nf()\n")

    def test_names_stay_variables_outside_list_sizes(self):
        # A literal zero divisor is a compile error, so folding b here would raise.
        with self.assertRaisesRegex(CompileError, "(?i)zero"):
            self.compile("x = 5\ny = x // 0\n")
        self.compile("b = 0\nx = 5\ny = x // b\n")

    def test_example_game_checks_on_the_flash_backend(self):
        code, out, err = run("check", str(REPO / "examples/catch"), "--target", "flash")
        self.assertEqual(code, 0, out + err)


class ConverterTests(Workspace):
    def test_bundled_ice_example_builds_after_conversion(self):
        code, out, err = run("convert-project", str(REPO / "examples/ice_project_example"), "-o", "out")
        self.assertEqual(code, 0, out + err)
        self.assertIn("The converted project compiles", out)
        self.assertEqual(load_project(self.root / "out").name, "ICEPROJE")

    def test_c_program_keeps_its_structure(self):
        code = cedev_to_python('''\
            #include <graphx.h>
            #include <ti/getcsc.h>
            #define SPEED 2
            int score = 0;
            int add(int a, int b) { return a + b; }
            int main(void) {
                uint8_t i;
                gfx_Begin();
                gfx_SetColor(gfx_red);
                for (i = 0; i < 10; i++) {
                    if (i % 2 == 0 && i != 4) {
                        gfx_SetPixel(i, i);
                    } else if (i > 7) {
                        score += add(i, 1);
                    } else {
                        score--;
                    }
                }
                while (!os_GetCSC());
                gfx_End();
                return 0;
            }
            ''')
        self.assertIn("    global _draw_color, score", code)
        self.assertIn("    for i in range(0, 10):", code)
        self.assertIn("        if i % 2 == 0 and i != 4:", code)
        self.assertIn("            graphics.pixel(i, i, _draw_color)", code)
        self.assertIn("        elif i > 7:", code)
        self.assertIn("    while not keyboard.get():\n        pass", code)
        compile(code, "converted", "exec")

    def test_converted_c_project_runs(self):
        self.write("cedev/makefile", "NAME = DEMOPROG\nSRC = src/main.c\n")
        self.write("cedev/src/helper.h", "#define LIMIT 5\nint twice(int v);\n")
        self.write("cedev/src/helper.c", '#include "helper.h"\nint twice(int v) { return v * 2; }\n')
        self.write("cedev/src/main.c", '''\
            #include "helper.h"
            int total = 0;
            int main(void) {
                int i;
                for (i = 0; i < LIMIT; i++) { total += twice(i); }
                return 0;
            }
            ''')
        code, out, err = run("convert-project", "cedev", "-o", "out")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(load_project(self.root / "out").name, "DEMOPROG")

        import sys
        sys.path.insert(0, str(REPO / "tests"))
        from asm_sim import run_program, variable
        from ti84asm.project import load_sources
        source, _ = load_sources(self.root / "out/src/main.py")
        sim, compiler = run_program(source, "ce")
        self.assertEqual(variable(sim, compiler, "total"), 20)

    def test_unsupported_code_becomes_a_visible_todo(self):
        self.write("cedev/src/main.c", '''\
            struct point { int x; };
            int main(void) {
                int *p = 0;
                switch (1) { case 1: break; }
                gfx_ScaledSprite(1, 2);
                return 0;
            }
            ''')
        code, out, err = run("convert-project", "cedev", "-o", "out", "-v")
        converted = (self.root / "out/src/main.py").read_text(encoding="utf-8")
        notes = (self.root / "out/CONVERSION_NOTES.md").read_text(encoding="utf-8")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(converted.count("TODO(convert)"), 4)
        self.assertIn("gfx_ScaledSprite", notes)
        self.assertIn("switch", notes)

    def test_missing_project_is_a_clean_error(self):
        code, _, err = run("convert-project", "nope")
        self.assertEqual(code, 1)
        self.assertIn("project not found", err)

    def test_detects_project_type(self):
        self.write("a/x.ice", "gfx_Begin()\n")
        code, out, _ = run("convert-project", "a", "-o", "out")
        self.assertIn("(ice)", out)
        self.assertEqual(code, 0)

    def test_ice_string_api(self):
        self.assertIn("graphics.begin()", ice_to_python("gfx_Begin()\n"))


if __name__ == "__main__":
    unittest.main()
