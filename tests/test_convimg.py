"""convimg must produce valid output for various formats.

Run with:  python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

from ti84asm.convimg import convert
from ti84asm.errors import CompileError


class ConvimgTests(unittest.TestCase):
    def test_rgb565_bin(self):
        """Test RGB565 binary output."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a simple 2x2 image (red, green, blue, white)
            image = Path(tmp) / "test.png"
            # We'll create a simple image programmatically using Pillow
            try:
                from PIL import Image
            except ImportError:
                self.skipTest("Pillow not installed")
            
            # Create a 2x2 RGBA image
            img = Image.new("RGBA", (2, 2))
            pixels = img.load()
            pixels[0, 0] = (255, 0, 0, 255)      # Red
            pixels[1, 0] = (0, 255, 0, 255)      # Green
            pixels[0, 1] = (0, 0, 255, 255)      # Blue
            pixels[1, 1] = (255, 255, 255, 255)  # White
            img.save(image)
            
            output = Path(tmp) / "out.bin"
            files = convert(image, output, "bin", "test_img")
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].is_file())
            # RGB565: 2 bytes per pixel, 2x2 = 4 pixels = 8 bytes
            self.assertEqual(files[0].stat().st_size, 8)

    def test_rgb565_8xv(self):
        """Test RGB565 AppVar output."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                from PIL import Image
            except ImportError:
                self.skipTest("Pillow not installed")
            
            image = Path(tmp) / "test.png"
            img = Image.new("RGBA", (2, 2))
            img.save(image)
            
            output = Path(tmp) / "out.8xv"
            files = convert(image, output, "8xv", "IMG")
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].is_file())
            # Should be a valid TI file with header
            data = files[0].read_bytes()
            self.assertTrue(data.startswith(b"**TI83F*"))

    def test_rgb565_c_array(self):
        """Test RGB565 C array output."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                from PIL import Image
            except ImportError:
                self.skipTest("Pillow not installed")
            
            image = Path(tmp) / "test.png"
            img = Image.new("RGBA", (2, 2))
            img.save(image)
            
            output = Path(tmp) / "out.c"
            files = convert(image, output, "c", "test_array")
            self.assertEqual(len(files), 1)
            content = files[0].read_text()
            self.assertIn("unsigned char test_array", content)
            self.assertIn("=", content)

    def test_unsupported_format(self):
        """Test that unsupported format raises error."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                from PIL import Image
            except ImportError:
                self.skipTest("Pillow not installed")
            
            image = Path(tmp) / "test.png"
            img = Image.new("RGBA", (2, 2))
            img.save(image)
            
            output = Path(tmp) / "out.xyz"
            with self.assertRaises(CompileError):
                convert(image, output, "xyz", "test")


if __name__ == "__main__":
    unittest.main()
