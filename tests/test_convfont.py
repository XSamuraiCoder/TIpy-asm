"""convfont must match CEdev's convfont v1.2.

Run with:  python -m unittest discover -s tests -v
"""
import contextlib
import io
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from ti84asm.cedev_config import get_prefix
from ti84asm.cli import main as cli_main
from ti84asm.convfont import FontError, main, parse_fnt, parse_text, serialize_font, serialize_fontpack
from ti84asm.errors import CompileError

TEXT_FONT = b"""convfont
Height: 2
Weight: Bold
Style: Serif
Style: Italic
Cap height: 1
Baseline: 2
Font Data:
Code point: 65
Data:
10
01
Code point: 0x42
Width: 10
Data:
1111111111
1
"""


def fnt_v2(height=2, widths=(3, 9), first=65):
    """Build a minimal version 2 Windows FNT."""
    table_end = 118 + 4 * len(widths)
    offsets, bitmaps = [], b""
    for index, width in enumerate(widths):
        offsets.append(table_end + len(bitmaps))
        columns = (width + 7) // 8
        bitmaps += bytes((0x80 + index + column * 2 + row) & 0xFF for column in range(columns) for row in range(height))
    size = table_end + len(bitmaps)
    header = bytearray(118)
    struct.pack_into("<HI", header, 0, 0x200, size)
    struct.pack_into("<H", header, 74, 1)
    struct.pack_into("<H", header, 88, height)
    header[95], header[96] = first, first + len(widths) - 1
    table = b"".join(struct.pack("<HH", width, offset) for width, offset in zip(widths, offsets))
    return bytes(header) + table + bitmaps


def run_quietly(function, arguments):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = function(arguments)
    return code, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):
    def test_text_font_layout(self):
        font = parse_text(TEXT_FONT)
        self.assertEqual((font.height, font.first_glyph, font.widths), (2, 65, [2, 10]))
        self.assertEqual((font.weight, font.style, font.cap_height, font.baseline_height), (0xC0, 5, 1, 2))
        data = serialize_font(font)
        self.assertEqual(data[:4], bytes((0, 2, 2, 65)))
        self.assertEqual(data[18:20], bytes((2, 10)))
        # Glyph A's rows, then glyph B's rows with each row's bytes reversed.
        self.assertEqual(data[-6:], bytes((0x80, 0x40, 0xC0, 0xFF, 0x00, 0x80)))

    def test_fnt_layout_and_ascent_as_baseline(self):
        font = parse_fnt(fnt_v2())
        self.assertEqual((font.height, font.first_glyph, font.widths, font.baseline_height), (2, 65, [3, 9], 1))
        # Column-major input becomes row-major.
        self.assertEqual(font.bitmaps[1], bytes((0x81, 0x83, 0x82, 0x84)))

    def test_fontpack_without_and_with_metadata(self):
        font = parse_text(TEXT_FONT)
        plain = serialize_fontpack([font])
        self.assertEqual(plain[:12], b"FONTPACK" + bytes((0, 0, 0, 1)))
        named = serialize_fontpack([font], {"N": b"Hi"})
        self.assertEqual(named[8:11], bytes((15, 0, 0)))
        self.assertIn(b"Hi\0", named)

    def test_bad_inputs_use_convfont_exit_codes(self):
        for data, code, message in ((b"notfont\n", 7, "does not start"), (b"convfont\nData:\n", 7, "height"),
                                    (b"convfont\nHeight: 1\nBogus: 1\nData:\n", 7, "Unrecognized"),
                                    (b"convfont\nHeight: 1\nData:\n", 7, "without reading")):
            with self.subTest(data=data):
                with self.assertRaisesRegex(FontError, message) as caught:
                    parse_text(data)
                self.assertEqual(caught.exception.code, code)
        with self.assertRaises(FontError) as caught:
            parse_fnt(b"\0\0\0\0")
        self.assertEqual(caught.exception.code, 1)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.text = self.root / "font.convfont"
        self.text.write_bytes(TEXT_FONT)
        self.output = self.root / "out"

    def test_metrics_apply_to_the_font_before_them(self):
        code, _, _ = run_quietly(main, ["-o", "binary", "-t", str(self.text), "-a", "1", "-w", "normal", "-s", "8", str(self.output)])
        self.assertEqual(code, 0)
        data = self.output.read_bytes()
        self.assertEqual((data[11], data[13], data[14]), (1, 0x80, 13))

    def test_option_errors_match_convfont(self):
        for arguments, message in ((["-a", "1", "-o", "binary"], "Must specify a font"),
                                   (["-o", "binary", "-t", "T", "-t", "T"], "multiple input fonts"),
                                   (["-o", "binary", "-N", "x"], "font pack output"),
                                   (["-o", "binary", "-t", "T", "-a", "65"], "too large"),
                                   (["-o", "binary", "-t", "T", "-l", "3"], "too large"),
                                   (["-o", "x"], "Unknown output format"), (["-q"], "Unknown option")):
            arguments = [str(self.text) if value == "T" else value for value in arguments] + [str(self.output)]
            with self.subTest(arguments=arguments):
                code, _, err = run_quietly(main, arguments)
                self.assertEqual(code, 4)
                self.assertIn(message, err)

    def test_failed_run_leaves_no_file(self):
        code, _, _ = run_quietly(main, ["-t", str(self.text), str(self.output)])
        self.assertEqual(code, 4)
        self.assertFalse(self.output.exists())

    def test_through_the_tipy_asm_command(self):
        code, out, _ = run_quietly(cli_main, ["convfont", "-o", "fontpack", "-t", str(self.text), "-N", "Hi", str(self.output)])
        self.assertEqual(code, 0, out)
        self.assertTrue(self.output.read_bytes().startswith(b"FONTPACK"))

    def test_ttf_is_refused_as_a_project_asset(self):
        from ti84asm.convfont import load_font

        ttf = self.root / "a.ttf"
        ttf.write_bytes(b"x")
        with self.assertRaisesRegex(CompileError, "separate tool"):
            load_font(ttf)


def cedev_convfont():
    try:
        tool = Path(get_prefix()) / "bin" / "convfont.exe"
    except CompileError:
        return None
    return tool if tool.is_file() else None


REAL = cedev_convfont()


@unittest.skipUnless(REAL, "CEdev is not installed")
class MatchesCedevTests(unittest.TestCase):
    """Compare with the real tool on the fonts CEdev ships."""

    def test_sample_fonts_produce_identical_files(self):
        examples = Path(get_prefix()) / "examples" / "library_examples" / "fontlibc"
        fnt = str(examples / "example" / "src" / "fonts" / "testfont.fnt")
        texts = sorted(str(path) for path in (examples / "font_pack" / "src" / "fonts").glob("*.convfont"))
        cases = [["-o", "binary", "-f", fnt], ["-o", "asmarray", "-f", fnt],
                 ["-o", "carray", "-f", fnt, "-a", "1", "-b", "1", "-w", "bold", "-c", "2", "-x", "9", "-l", "0x0B", "-Z"],
                 ["-o", "fontpack", "-N", "Dr. Sans", "-P", "Calculator 1252"] + sum((["-t", text] for text in texts), [])]
        cases += [["-o", kind, "-t", text] for kind in ("binary", "carray", "asmarray") for text in texts]
        with tempfile.TemporaryDirectory() as folder:
            theirs, ours = Path(folder) / "theirs", Path(folder) / "ours"
            for case in cases:
                with self.subTest(case=case):
                    subprocess.run([str(REAL), *case, str(theirs)], check=True, capture_output=True)
                    code, _, err = run_quietly(main, [*case, str(ours)])
                    self.assertEqual(code, 0, err)
                    self.assertEqual(ours.read_bytes(), theirs.read_bytes())


if __name__ == "__main__":
    unittest.main()
