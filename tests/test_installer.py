"""The built-in Flash App installer must do exactly what CE-Programming/app_tools' installer does.

The flash routines cannot run in the simulator, so hooks stand in for them and record
every write, erase, and delete. `reference_install` is upstream's main.c install() and
check_variable_overlaps(), transliterated to Python; the compiled installer must issue
the same operations in the same order for every layout.

Run with:  python -m unittest discover -s tests -v
"""
import random
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from asm_sim import Sim

from ti84asm.compiler import Compiler
from ti84asm.flashapp import default_appvar_prefix, write_installer_sources

SUCCESS, ALREADY_INSTALLED, MISSING_VAR, PORT_SETUP_FAILED, NO_SPACE = range(5)
MESSAGES = {SUCCESS: "Successfully installed.", ALREADY_INSTALLED: "Already installed.",
            MISSING_VAR: "Missing an AppVar.", PORT_SETUP_FAILED: "Unsupported OS version.",
            NO_SPACE: "Out of archive space."}
BAKED_NAME, COPIED_NAME = 0x111111, 0x222222
ENTER, CLEAR = 9, 15


@dataclass
class Layout:
    prefix: str
    split: int
    appvars: list            # (address of the size word, size)
    app_end: int
    vat: list                # (name, data address)
    installed: bool = False  # app_installed finds the app named in the AppVar
    baked_installed: bool = False
    ports_ok: bool = True
    ops: list = field(default_factory=list)
    calls: list = field(default_factory=list)


def strncmp(a: str, b: str, n: int) -> int:
    for k in range(n):
        ca = ord(a[k]) if k < len(a) else 0
        cb = ord(b[k]) if k < len(b) else 0
        if ca != cb:
            return ca - cb
        if ca == 0:
            return 0
    return 0


def reference_install(layout: Layout) -> tuple[int, list]:
    """CE-Programming/app_tools installer/src/main.c, install(), in Python."""
    ops = []
    if not layout.ports_ok:
        return PORT_SETUP_FAILED, ops
    app_size = 0
    appvars = []
    for i in range(99):
        if i >= len(layout.appvars):
            return MISSING_VAR, ops
        address, size = layout.appvars[i]
        entry = {"data": address + 2, "size": size, "offset": app_size}
        if i == 0 and layout.installed:
            return ALREADY_INSTALLED, ops
        app_size += size
        appvars.append(entry)
        if size != layout.split:
            break
    appvars[-1]["size"] += 3
    app_end = layout.app_end
    app_start = app_end - app_size - 3

    first_erased_page = ((app_start >> 16) - 1) & 0xFF
    for name, data in layout.vat:
        if data >= 0xD00000:
            continue
        page = (data >> 16) & 0xFF
        if page < first_erased_page:
            continue
        ours = False
        for i in range(99):
            if strncmp(name, f"{layout.prefix}{i}", len(name)) == 0:
                if page >= ((app_start + layout.split * i) >> 16) & 0xFF:
                    return NO_SPACE, ops
                ours = True
                break
        if not ours:
            return NO_SPACE, ops

    written, wrote_size, index = app_end, False, len(appvars) - 1
    page = (app_end >> 16) & 0xFF
    while page >= (app_start >> 16) & 0xFF and index >= 0:
        while written > page << 16 and index >= 0:
            appvar = appvars[index]
            seg_start = app_start + appvar["offset"]
            dst_end = min(seg_start + appvar["size"], (page + 1) << 16)
            dst_start = max(seg_start, page << 16)
            src_start = appvar["data"] + (dst_start - seg_start)
            if not wrote_size:
                ops.append(("write", src_start, dst_start, dst_end - dst_start - 3))
                ops.append(("size", dst_end - 3, app_size))
                wrote_size = True
            else:
                ops.append(("write", src_start, dst_start, dst_end - dst_start))
            written = dst_start
            if dst_start == seg_start:
                index -= 1
        ops.append(("erase", (page - 1) & 0xFF))
        page = (page - 1) & 0xFF
    ops.append(("fix", app_start))
    return SUCCESS, ops


def hooks_for(layout: Layout) -> dict:
    sizes = {address: size for address, size in layout.appvars}
    state = {"entry": 0}

    def arg(sim, register):
        return sim.r[register]

    def ret(sim, value):
        sim.r["hl"] = value & sim.mask

    def record(*op):
        layout.ops.append(op)

    def traced(name, function):
        def hook(sim):
            layout.calls.append(name)
            function(sim)
        return hook

    def appvar_data(sim):
        index = arg(sim, "hl")
        ret(sim, layout.appvars[index][0] if index < len(layout.appvars) else 0)

    def app_installed(sim):
        name = arg(sim, "hl")
        found = layout.baked_installed if name == BAKED_NAME else layout.installed if name == COPIED_NAME else None
        assert found is not None, f"app_installed got an unexpected name pointer {name:#x}"
        ret(sim, 1 if found else 0)

    def vat_next(sim):
        state["entry"] += 1
        ret(sim, state["entry"] if state["entry"] <= len(layout.vat) else 0)

    def vat_entry():
        return layout.vat[state["entry"] - 1]

    def vat_name_char(sim):
        name = vat_entry()[0]
        position = arg(sim, "hl")
        ret(sim, ord(name[position]) if position < len(name) else 0)

    hooks = {
        "installer_begin": lambda sim: None,
        "installer_end": lambda sim: None,
        "port_setup": lambda sim: ret(sim, 0 if layout.ports_ok else 1),
        "appvar_data": appvar_data,
        "peek16": lambda sim: ret(sim, sizes[arg(sim, "hl")]),
        "copy_app_name": lambda sim: ret(sim, COPIED_NAME),
        "app_name": lambda sim: ret(sim, BAKED_NAME),
        "app_installed": app_installed,
        "find_last_app": lambda sim: ret(sim, layout.app_end),
        "vat_start": lambda sim: (state.__setitem__("entry", 0), ret(sim, 1)),
        "vat_next": vat_next,
        "vat_data": lambda sim: ret(sim, vat_entry()[1]),
        "vat_name_length": lambda sim: ret(sim, len(vat_entry()[0])),
        "vat_name_char": vat_name_char,
        "flash_write": lambda sim: record("write", arg(sim, "hl"), arg(sim, "de"), arg(sim, "bc")),
        "flash_write_size": lambda sim: record("size", arg(sim, "hl"), arg(sim, "de")),
        "flash_erase": lambda sim: record("erase", arg(sim, "hl") & 0xFF),
        "fix_relocations": lambda sim: record("fix", arg(sim, "hl")),
        "delete_app": lambda sim: (record("delete_app", arg(sim, "hl")), ret(sim, 1)),
        "delete_appvar": lambda sim: record("delete_appvar", arg(sim, "hl")),
        "delete_installer": lambda sim: record("delete_installer"),
        "put_str": lambda sim: None,
        "clear_home": lambda sim: None,
    }
    return {name: traced(name, function) for name, function in hooks.items()}


class InstallerTests(unittest.TestCase):
    assemblies: dict = {}

    def assembly(self, prefix: str, split: int) -> str:
        key = (prefix, split)
        if key not in self.assemblies:
            with tempfile.TemporaryDirectory() as folder:
                source = write_installer_sources(Path(folder), "HELLO", prefix, split, "INSTALL")
                self.assemblies[key] = Compiler("INSTALL", "ce", source_dir=Path(folder)).compile(source)
        return self.assemblies[key]

    def run_installer(self, layout: Layout, keys=(0, CLEAR)) -> Sim:
        sim = Sim(self.assembly(layout.prefix, layout.split), "ce", keys=list(keys), hooks=hooks_for(layout))
        sim.run(limit=20_000_000)
        self.assertEqual(sim.exit_sp, sim.sp_start)
        return sim

    def result_of(self, sim: Sim) -> int:
        matches = [code for code, message in MESSAGES.items() if message in sim.output]
        self.assertEqual(len(matches), 1, sim.output)
        return matches[0]

    def random_layout(self, rng: random.Random) -> Layout:
        prefix = rng.choice(["HELLO", "TIPY", "A"])
        split = rng.choice([65200, 30000, 12345])
        count = rng.randint(1, 4)
        sizes = [split] * (count - 1) + [rng.randint(1, split - 1)]
        if rng.random() < 0.08:
            sizes[-1] = split                       # no short last part, so one is missing
        appvars = [(rng.choice([0xD10000, 0x0C0000]) + rng.randrange(0x8000) + index * 0x10000, size)
                   for index, size in enumerate(sizes)]
        app_end = rng.randint(0x200000, 0x3B0000)
        names = [f"{prefix}{index}" for index in range(count)] + ["HEL", f"{prefix}9", "OTHER", "", prefix]
        vat = [(rng.choice(names), rng.choice([0xD20000 + rng.randrange(0x10000), rng.randrange(0x0C0000, 0x3C0000)]))
               for _ in range(rng.randrange(6))]
        return Layout(prefix, split, appvars, app_end, vat, installed=rng.random() < 0.08,
                      ports_ok=rng.random() > 0.05)

    def test_matches_upstream_on_random_layouts(self):
        rng = random.Random(2026)
        seen = set()
        for case in range(300):
            layout = self.random_layout(rng)
            expected_code, expected_ops = reference_install(layout)
            with self.subTest(case=case, layout=layout):
                sim = self.run_installer(layout)
                self.assertEqual(self.result_of(sim), expected_code)
                self.assertEqual(layout.ops, expected_ops)
            seen.add(expected_code)
        self.assertEqual(seen, {SUCCESS, ALREADY_INSTALLED, MISSING_VAR, PORT_SETUP_FAILED, NO_SPACE})

    def test_writes_cross_page_boundaries_in_upstream_order(self):
        layout = Layout("HELLO", 30000, [(0x0C1000, 30000), (0x0D1000, 30000), (0x0E1000, 20000)], 0x3A8000, [])
        expected_code, expected_ops = reference_install(layout)
        sim = self.run_installer(layout)
        self.assertEqual(expected_code, SUCCESS)
        self.assertEqual(layout.ops, expected_ops)
        self.assertGreaterEqual(sum(op[0] == "erase" for op in layout.ops), 2)

    def test_text_buffer_is_off_before_ports_are_set_up(self):
        layout = Layout("HELLO", 65200, [(0xD10000, 1000)], 0x3A0000, [])
        self.run_installer(layout)
        self.assertEqual(layout.calls[0], "installer_begin")
        self.assertLess(layout.calls.index("installer_begin"), layout.calls.index("port_setup"))
        self.assertEqual(layout.calls[-1], "installer_end")

    def test_success_can_delete_installer_files(self):
        layout = Layout("HELLO", 65200, [(0xD10000, 1000)], 0x3A0000, [])
        self.run_installer(layout, keys=(0, ENTER))
        deletes = [op for op in layout.ops if op[0].startswith("delete")]
        self.assertEqual(deletes, [("delete_installer",), ("delete_appvar", 0)])

    def test_installed_app_is_offered_for_deletion(self):
        layout = Layout("HELLO", 65200, [(0xD10000, 1000)], 0x3A0000, [], baked_installed=True)
        sim = self.run_installer(layout, keys=(0, ENTER, 0, ENTER))
        self.assertIn("is installed.", sim.output)
        self.assertEqual(layout.ops, [("delete_app", BAKED_NAME)])
        self.assertIn("deleted.", sim.output)

    def test_declining_deletion_changes_nothing(self):
        layout = Layout("HELLO", 65200, [], 0x3A0000, [], baked_installed=True)
        self.run_installer(layout, keys=(0, CLEAR))
        self.assertEqual(layout.ops, [])

    def test_installer_deletes_itself_with_its_real_variable_type(self):
        from ti84asm.flashapp import build_installer

        with tempfile.TemporaryDirectory() as folder:
            program = build_installer(Path(folder) / "INSTALL.8xp", "HELLO", "HELLO", 65200, "INSTALL").read_bytes()
        built_type, built_name = program[0x3B], program[0x3C:0x44].rstrip(b"\0")
        sim = Sim(self.assembly("HELLO", 65200), "ce")
        address = sim.labels["inst_program_name"]
        searched = bytes(sim.read(address + offset) for offset in range(1 + len(built_name)))
        self.assertEqual(searched, bytes([built_type]) + built_name)

    def run_app_search(self, apps: list, keys) -> tuple[Sim, list]:
        """Run the real app_installed and delete_app with FindAppUp listing `apps`."""
        layout = Layout("HELLO", 65200, [], 0x3A0000, [])
        hooks = hooks_for(layout)
        del hooks["app_installed"], hooks["delete_app"], hooks["app_name"]
        state = {"next": 0}
        deleted = []

        def find_app_up(sim):
            # The OS walks installed apps in order; it skips deleted ones, so they are not listed.
            if state["next"] >= len(apps):
                sim.C = True
                return
            name = apps[state["next"]].encode().ljust(8, b"\0")
            for offset, value in enumerate(name):
                sim.write(sim.value("ti.OP1") + 1 + offset, value)
            sim.r["de"] = 0x300000 + state["next"]
            state["next"] += 1
            sim.C = False

        hooks.update({
            "ti.ZeroOP3": lambda sim: state.__setitem__("next", 0),
            "ti.OP3ToOP1": lambda sim: None,
            "ti.OP1ToOP3": lambda sim: None,
            "ti.FindAppUp": find_app_up,
            "ti.DeleteApp": lambda sim: deleted.append(sim.r["hl"]),
        })
        sim = Sim(self.assembly("HELLO", 65200), "ce", keys=list(keys), hooks=hooks)
        sim.run(limit=20_000_000)
        self.assertEqual(sim.exit_sp, sim.sp_start)
        return sim, deleted

    def test_app_search_matches_whole_names_from_find_app_up(self):
        sim, deleted = self.run_app_search(["HELL", "HELLOX", "CABRI", "HELLO"], keys=(0, ENTER, 0, ENTER))
        self.assertIn("is installed.", sim.output)
        self.assertEqual(deleted, [0x300003])

    def test_app_missing_from_find_app_up_is_not_installed(self):
        # A deleted app waiting for the archive cleanup is not listed by FindAppUp.
        sim, deleted = self.run_app_search(["HELL", "HELLOX", "CABRI"], keys=(0, CLEAR))
        self.assertNotIn("is installed.", sim.output)
        self.assertEqual(deleted, [])

    def test_default_prefix_comes_from_the_app_name(self):
        self.assertEqual(default_appvar_prefix("HELLO"), "HELLO")
        self.assertEqual(default_appvar_prefix("MY_GAME1"), "MYGAME")
        self.assertEqual(default_appvar_prefix("1APP"), "TIPY")


if __name__ == "__main__":
    unittest.main()
