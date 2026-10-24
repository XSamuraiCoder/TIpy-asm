"""convfont must produce valid output for various formats.

Run with:  python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

from ti84asm.convfont import convert
from ti84asm.errors import CompileError


class ConvfontTests(unittest.TestCase):
    def test_fnt_to_bin(self):
        """Test converting .fnt file to binary."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a simple .fnt file
            fnt = Path(tmp) / "test.fnt"
            # Minimal FNT header
            fnt_data = b'\x00' * 16  # Simplified for testing
            fnt.write_bytes(fnt_data)
            
            output = Path(tmp) / "out.bin"
            result = convert(fnt, output, "bin", "test_font")
            self.assertEqual(result, output)
            self.assertTrue(output.is_file())

    def test_fnt_to_8xv(self):
        """Test converting .fnt file to AppVar."""
        with tempfile.TemporaryDirectory() as tmp:
            fnt = Path(tmp) / "test.fnt"
            fnt.write_bytes(b'\x00' * 16)
            
            output = Path(tmp) / "out.8xv"
            result = convert(fnt, output, "8xv", "FONT")
            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
            # Should be a valid TI file with header
            data = output.read_bytes()
            self.assertTrue(data.startswith(b"**TI83F*"))

    def test_unsupported_format(self):
        """Test that unsupported format raises error."""
        with tempfile.TemporaryDirectory() as tmp:
            fnt = Path(tmp) / "test.fnt"
            fnt.write_bytes(b'\x00' * 16)
            
            output = Path(tmp) / "out.xyz"
            with self.assertRaises(CompileError):
                convert(fnt, output, "xyz", "test")

    def test_ttf_requires_size(self):
        """Test that TTF without size raises error."""
        with tempfile.TemporaryDirectory() as tmp:
            # We don't need an actual TTF file for this test
            # The error should be raised before trying to read the file
            ttf = Path(tmp) / "test.ttf"
            ttf.write_bytes(b'\x00' * 16)
            
            output = Path(tmp) / "out.8xv"
            with self.assertRaises(CompileError):
                convert(ttf, output, "8xv", "test", size=None)


if __name__ == "__main__":
    unittest.main()
