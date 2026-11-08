"""The star, dice, and walk examples build and behave as their docstrings say.

Run with:  python -m unittest discover -s tests -v
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from asm_sim import Sim

from ti84asm.compiler import Compiler
from ti84asm.project import build_assets, load_project, load_sources

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
ENTER, CLEAR, DEL = 9, 15, 56
LEFT, RIGHT, UP, DOWN = 2, 3, 4, 1
WHITE = 0xFFFF


def compile_example(name: str, target: str) -> str:
    source, _ = load_sources(EXAMPLES / name / "src/main.py")
    return Compiler(name.upper(), target, source_dir=EXAMPLES / name / "src").compile(source)


def after_frames(frames: int, keys: set, then=None):
    """A _rt_delay hook: hold `keys` from the start, then CLEAR after `frames` delays."""
    state = {"frames": 0}

    def hook(sim):
        if state["frames"] == 0:
            sim.held |= keys
        state["frames"] += 1
        if then:
            then(sim, state["frames"])
        if state["frames"] >= frames:
            sim.held = {CLEAR}
    return hook, state


class StarTests(unittest.TestCase):
    def test_spins_and_quits_on_both_targets(self):
        for target in ("ce", "classic"):
            with self.subTest(target=target):
                hook, state = after_frames(5, {RIGHT})
                sim = Sim(compile_example("star", target), target, hooks={"_rt_delay": hook})
                sim.run(20_000_000)
                self.assertEqual(state["frames"], 5)
                # Speed starts at 3 and is read before each frame. RIGHT is pressed
                # after the first frame, so the next four frames each add one.
                self.assertEqual(sim.output, "Final speed: 7\n")

    def test_draws_the_star_points_on_ce(self):
        seen = []

        def look(sim, frame):
            if frame == 1:
                def near(x, y):
                    return any(sim.vram(x + dx, y + dy) != WHITE for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                # The first frame starts at 90 degrees: the top point, then 72 degrees on.
                seen.extend([near(160, 6), near(51, 85), near(269, 85), near(160, 120)])

        hook, _ = after_frames(1, set(), look)
        sim = Sim(compile_example("star", "ce"), "ce", hooks={"_rt_delay": hook})
        sim.run(20_000_000)
        self.assertEqual(seen, [True, True, True, False])


class DiceTests(unittest.TestCase):
    def run_dice(self, target: str, keys, appvars=None) -> Sim:
        # keyboard.read() waits for every key to be released before the next press.
        presses = [code for key in keys for code in (0, key)]
        sim = Sim(compile_example("dice", target), target, keys=presses, appvars=appvars)
        sim.run(20_000_000)
        return sim

    def test_rolls_are_counted_and_kept(self):
        for target in ("ce", "classic"):
            with self.subTest(target=target):
                sim = self.run_dice(target, [ENTER, ENTER, ENTER, CLEAR])
                rolls = [line for line in sim.output.splitlines() if line.startswith("Rolled")]
                self.assertEqual(len(rolls), 3)
                stats = sim.appvar("DICESTAT")
                self.assertEqual(len(stats), 26)
                counts = [stats[2 * i] | stats[2 * i + 1] << 8 for i in range(13)]
                self.assertEqual(counts[0], 3)
                self.assertEqual(sum(counts[2:]), 3)
                for line in rolls:
                    words = line.split()
                    first, second, total = int(words[1]), int(words[3]), int(words[5])
                    self.assertTrue(1 <= first <= 6 and 1 <= second <= 6)
                    self.assertEqual(first + second, total)
                    self.assertIn(f"{total} came up", sim.output)
                self.assertIn("Rolls: 3", sim.output)

    def test_stats_carry_over_and_del_clears_them(self):
        saved = bytes([5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0] + [0] * 10)
        sim = self.run_dice("ce", [CLEAR], appvars={"DICESTAT": saved})
        self.assertIn("Rolls: 5", sim.output)
        self.assertIn("7 came up 5", sim.output)
        sim = self.run_dice("ce", [DEL, CLEAR], appvars={"DICESTAT": saved})
        self.assertIn("Stats cleared", sim.output)
        self.assertIn("Rolls: 0", sim.output)
        self.assertEqual(sim.appvar("DICESTAT"), bytes(26))


def appvar_data(path: Path) -> bytes:
    """The data of the single variable in an .8xv file."""
    raw = path.read_bytes()
    header = raw[55] | raw[56] << 8
    start = 57 + header
    # The variable's data starts with its own 2-byte length, which the simulator adds back.
    length = raw[start + 2] | raw[start + 3] << 8
    return raw[start + 4:start + 4 + length]


class WalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import PIL  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Pillow is not installed")
        cls.folder = tempfile.TemporaryDirectory()
        project = Path(cls.folder.name) / "walk"
        shutil.copytree(EXAMPLES / "walk", project, ignore=shutil.ignore_patterns("bin"))
        written, _ = build_assets(load_project(project))
        cls.hero = appvar_data(written[0])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_hero_asset_is_a_16_by_16_sprite(self):
        self.assertEqual(self.hero[:4], bytes([16, 0, 16, 0]))

    def test_walks_right_and_stays_on_screen(self):
        # The hero only waits between steps while it moves, so hold RIGHT from the start.
        hook, _ = after_frames(80, set())
        sim = Sim(compile_example("walk", "ce"), "ce", held={RIGHT}, appvars={"HERO": self.hero},
                  hooks={"_rt_delay": hook})
        sim.run(60_000_000)
        # 80 steps of 2 pixels from x = 152 would pass the edge; the hero stops at x = 320 - 16.
        row = 120 - 8 + 4     # the hero's eyes are on its fourth row
        drawn = [x for x in range(320) if sim.vram(x, row) != WHITE]
        self.assertTrue(drawn)
        self.assertEqual(max(drawn), 304 + 11)
        self.assertGreaterEqual(min(drawn), 304)

    def test_missing_sprite_says_so(self):
        sim = Sim(compile_example("walk", "ce"), "ce")
        sim.run(5_000_000)
        self.assertEqual(sim.output, "Send HERO.8xv too\n")


def needs_pillow(test_class):
    try:
        import PIL  # noqa: F401
    except ImportError:
        return unittest.skip("Pillow is not installed")(test_class)
    return test_class


class BuiltExample:
    """An example copied to a temporary folder, with its assets built there."""

    def __init__(self, name: str):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name) / name
        shutil.copytree(EXAMPLES / name, self.root, ignore=shutil.ignore_patterns("bin", "sprites.py"))
        self.config = load_project(self.root)
        written, _ = build_assets(self.config)
        self.appvars = {path.stem: appvar_data(path) for path in written if path.suffix == ".8xv"}

    def compile(self, target: str) -> tuple[str, Compiler]:
        source, _ = load_sources(self.config.main)
        compiler = Compiler(self.config.name, target, source_dir=self.config.main.parent)
        return compiler.compile(source), compiler

    def close(self):
        self.folder.cleanup()


@needs_pillow
class CoinsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = BuiltExample("coins")
        cls.assembly, cls.compiler = cls.example.compile("ce")

    @classmethod
    def tearDownClass(cls):
        cls.example.close()

    def test_each_storage_builds_where_it_says(self):
        self.assertEqual(sorted(self.example.appvars), ["HERO", "TILES"])
        tiles = self.example.appvars["TILES"]
        # Grass then flower, one after another: each is 16 by 16, 4 + 512 bytes.
        self.assertEqual(len(tiles), 2 * (4 + 16 * 16 * 2))
        self.assertEqual(tiles[516:520], bytes([16, 0, 16, 0]))
        module = (self.example.root / "src/sprites.py").read_text(encoding="utf-8")
        self.assertIn("GRASS = 0\n", module)
        self.assertIn("FLOWER = 1\n", module)
        self.assertIn("COIN = (\n", module)

    def test_hero_collects_a_coin(self):
        compiler = self.compiler
        coin = compiler.array_labels["coin"]

        def steer(sim):
            score = sim.word(compiler.variables["main.score"])
            if score:
                sim.held = {CLEAR}
                return
            coin_x = sim.read(sim.labels[coin], 3)
            coin_y = sim.read(sim.labels[coin] + 3, 3)
            x = sim.word(compiler.variables["main.x"])
            y = sim.word(compiler.variables["main.y"])
            if abs(x + 8 - coin_x - 6) > 1:
                sim.held = {RIGHT if x + 8 < coin_x + 6 else LEFT}
            else:
                sim.held = {DOWN if y + 8 < coin_y + 6 else UP}

        sim = Sim(self.assembly, "ce", held={RIGHT}, appvars=self.example.appvars, hooks={"_rt_delay": steer})
        sim.run(200_000_000)
        self.assertEqual(sim.output, "Coins: 1\n")

    def test_tiles_come_from_the_pack(self):
        def stop(sim):
            sim.held = {CLEAR}

        sim = Sim(self.assembly, "ce", held={RIGHT}, appvars=self.example.appvars, hooks={"_rt_delay": stop})
        sim.run(60_000_000)
        flower_center = 0xFE85      # the yellow middle of the flower tile, at (7, 4)
        # Row 5, column 0 is a flower tile: (0 * 7 + 5 * 3) % 5 == 0.
        self.assertEqual(sim.vram(7, 5 * 16 + 4), flower_center)
        self.assertNotEqual(sim.vram(16 + 7, 5 * 16 + 4), flower_center)

    def test_missing_appvars_are_reported(self):
        sim = Sim(self.assembly, "ce")
        sim.run(5_000_000)
        self.assertEqual(sim.output, "Send HERO.8xv and\nTILES.8xv too\n")


@needs_pillow
class BounceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = BuiltExample("bounce")

    @classmethod
    def tearDownClass(cls):
        cls.example.close()

    def test_needs_no_appvar(self):
        self.assertEqual(self.example.appvars, {})

    def test_bounces_on_both_targets(self):
        # The ball starts at (3, 5) going down and right. On the classic screen it
        # reaches the bottom (64 - 8) after 51 moves; the CE screen is far bigger.
        for target, bounces in (("ce", 0), ("classic", 1)):
            with self.subTest(target=target):
                assembly, _ = self.example.compile(target)
                hook, _ = after_frames(60, set())
                sim = Sim(assembly, target, hooks={"_rt_delay": hook})
                sim.run(30_000_000)
                self.assertEqual(sim.output, f"Bounces: {bounces}\n")

    def test_ball_is_drawn_from_the_png(self):
        seen = []

        def look(sim, frame):
            if frame == 1:
                seen.append(sim.vram(3 + 3, 5 + 3))     # the ball's red middle

        hook, _ = after_frames(1, set(), look)
        assembly, _ = self.example.compile("ce")
        sim = Sim(assembly, "ce", hooks={"_rt_delay": hook})
        sim.run(30_000_000)
        red = ((220 >> 3) << 11) | ((50 >> 2) << 5) | (50 >> 3)
        self.assertEqual(seen, [red])


@needs_pillow
class SpriteStorageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "src").mkdir()
        (self.root / "src/main.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "assets").mkdir()
        shutil.copy(EXAMPLES / "coins/assets/coin.png", self.root / "assets/coin.png")

    def config(self, assets: str):
        (self.root / "pyproject.toml").write_text(f'[tool.tipy]\nname = "T"\n\n{assets}', encoding="utf-8")
        return load_project(self.root)

    def test_storage_defaults_and_pack_implies_pack(self):
        config = self.config('[[tool.tipy.assets]]\nsource = "assets/coin.png"\n\n'
                             '[[tool.tipy.assets]]\nsource = "assets/coin.png"\nname = "C2"\npack = "ALL"\n')
        self.assertEqual([(a.storage, a.name, a.pack) for a in config.assets],
                         [("appvar", "COIN", None), ("pack", "C2", "ALL")])

    def test_bad_storage_settings_are_reported(self):
        from ti84asm.errors import CompileError

        cases = {
            'storage = "disk"': "storage must be one of",
            'storage = "pack"': "go together",
            'kind = "binary"\nstorage = "program"': "for sprites only",
            'storage = "program"\nmodule = "my-sprites"': "must be a Python name",
            'storage = "program"\nname = "9LIVES"': "starting with a letter",
        }
        for extra, message in cases.items():
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(CompileError, message):
                    self.config(f'[[tool.tipy.assets]]\nsource = "assets/coin.png"\n{extra}\n')

    def test_pack_cannot_share_a_name_with_an_appvar(self):
        from ti84asm.errors import CompileError

        with self.assertRaisesRegex(CompileError, "both a pack and"):
            self.config('[[tool.tipy.assets]]\nsource = "assets/coin.png"\nname = "ALL"\n\n'
                        '[[tool.tipy.assets]]\nsource = "assets/coin.png"\nname = "C2"\npack = "ALL"\n')

    def test_a_hand_written_module_is_never_overwritten(self):
        from ti84asm.errors import CompileError
        from ti84asm.project import generate_asset_modules

        config = self.config('[[tool.tipy.assets]]\nsource = "assets/coin.png"\nstorage = "program"\n')
        (self.root / "src/sprites.py").write_text("MINE = 1\n", encoding="utf-8")
        with self.assertRaisesRegex(CompileError, "was not generated by tipy-asm"):
            generate_asset_modules(config)
        self.assertEqual((self.root / "src/sprites.py").read_text(encoding="utf-8"), "MINE = 1\n")

    def test_module_is_only_rewritten_when_it_changes(self):
        from ti84asm.project import generate_asset_modules

        config = self.config('[[tool.tipy.assets]]\nsource = "assets/coin.png"\nstorage = "program"\n')
        self.assertEqual(generate_asset_modules(config), [self.root / "src/sprites.py"])
        self.assertEqual(generate_asset_modules(config), [])

    def test_check_generates_the_module_first(self):
        import os
        import subprocess

        self.config('[[tool.tipy.assets]]\nsource = "assets/coin.png"\nstorage = "program"\n')
        (self.root / "src/main.py").write_text(
            "from ti84 import graphics\nfrom sprites import COIN\n\ngraphics.sprite(COIN, 1, 2)\n", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(REPO))
        result = subprocess.run([sys.executable, "-m", "ti84asm", "check", "--target", "both"], cwd=self.root,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pack_sprites_load_by_index(self):
        from asm_sim import run_program, variable

        source = ('from ti84 import sprite\na = sprite.load("PACK", 0)\nb = sprite.load("PACK", 1)\n'
                  'c = sprite.load("PACK", 2)\nw = sprite.width(b)\nd = sprite.load("PACK")\n')
        pack = bytes([1, 0, 1, 0, 0x34, 0x12, 2, 0, 1, 0, 1, 0, 2, 0])
        for archived in (False, True):
            with self.subTest(archived=archived):
                compiler = Compiler("T", "ce")
                sim = Sim(compiler.compile(source), "ce", appvars={"PACK": pack})
                if archived:
                    sim.archive("PACK")
                sim.run(3_000_000)
                a, b, c, d, w = (sim.word(compiler.variables[name]) for name in "abcdw")
                self.assertNotEqual(a, 0)
                self.assertEqual((b - a, c, d, w), (6, 0, a, 2))


if __name__ == "__main__":
    unittest.main()
