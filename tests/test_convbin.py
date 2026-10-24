"""convbin must produce exactly the bytes CEdev's own convbin produces.

The expected values below were captured from CEdev's convbin on the same input.
Run with:  python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

from ti84asm.convbin import ConvbinJob, convert
from ti84asm.errors import CompileError

DATA = bytes([1, 2, 3, 250, 251, 252, 0, 7])
GOLDEN = {
    '8xp': bytes.fromhex('2a2a54493833462a1a0a000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b000d000a000650726f670000000000000a000800010203fafbfc0007c504'),
    '8xv': bytes.fromhex('2a2a54493833462a1a0a000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b000d000a0015566172730000000000800a000800010203fafbfc00075805'),
    'c': bytes.fromhex('756e7369676e65642063686172206172725b385d203d0a7b0a20202020307830312c307830322c307830332c307866612c307866622c307866632c307830302c307830370a7d3b0a'),
    'asm': bytes.fromhex('6172723a0a3b20382062797465730a096462092430312c2430322c2430332c2466612c2466622c2466632c2430302c2430370a'),
    'ice': bytes.fromhex('617272207c20382062797465730a2230313032303346414642464330303037220a'),
}


class ConvbinTests(unittest.TestCase):
    def run_job(self, fmt, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.bin"
            src.write_bytes(DATA)
            out = Path(tmp) / f"o.{fmt}"
            convert(ConvbinJob(inputs=[(src, "bin")], output=out, oformat=fmt, **kw))
            return out.read_bytes()

    def test_8xp(self):
        self.assertEqual(self.run_job("8xp", name="Prog"), GOLDEN["8xp"])

    def test_8xv_archived(self):
        self.assertEqual(self.run_job("8xv", name="Vars", archive=True), GOLDEN["8xv"])

    def test_c_array(self):
        self.assertEqual(self.run_job("c", name="arr"), GOLDEN["c"])

    def test_asm_array(self):
        self.assertEqual(self.run_job("asm", name="arr"), GOLDEN["asm"])

    def test_ice_array(self):
        self.assertEqual(self.run_job("ice", name="arr"), GOLDEN["ice"])

    def test_split_names_and_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.bin"
            src.write_bytes(bytes(10000))
            out = Path(tmp) / "pack.8xv"
            files = convert(ConvbinJob(inputs=[(src, "bin")], output=out, oformat="8xv-split", name="Dat", max_var_size=4096))
            self.assertEqual([f.name for f in files], ["pack.0.8xv", "pack.1.8xv", "pack.2.8xv"])

    def test_split_minimum(self):
        with self.assertRaises(CompileError):
            self.run_job("8xv-split", name="Dat", max_var_size=100)

    def test_unsupported_format_is_an_error(self):
        with self.assertRaises(CompileError):
            self.run_job("zip")


if __name__ == "__main__":
    unittest.main()
