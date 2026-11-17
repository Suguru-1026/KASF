import ast
import unittest
from pathlib import Path


class TestTimeDomainOnly(unittest.TestCase):
    def test_solver_sources_do_not_call_fft_or_stft(self):
        root = Path(__file__).resolve().parents[1] / "krm_td_csc"
        blocked = {"fft", "rfft", "irfft", "fft2", "stft", "istft", "dct"}
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.lower() in blocked:
                    self.fail(f"frequency transform call/reference in {path.name}: {node.attr}")


if __name__ == "__main__":
    unittest.main()
