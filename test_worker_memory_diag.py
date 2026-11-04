"""Isolated tests for opt-in memory diagnostics; no production imports or network."""
import ast
import pathlib
import unittest
from unittest.mock import mock_open, patch

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = (ROOT / "production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


class MemoryDiagnosticTests(unittest.TestCase):
    def test_source_compiles(self):
        compile(SOURCE, str(ROOT / "production_worker_v2_shared_ws.py"), "exec")

    def test_disabled_by_default(self):
        self.assertIn('os.environ.get("MEM_DIAG_ENABLED", "0") == "1"', SOURCE)

    def test_rss_parser(self):
        fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_rss_mib")
        namespace = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<isolated>", "exec"), namespace)
        with patch("builtins.open", mock_open(read_data="Name: python\nVmRSS: 102400 kB\n")):
            self.assertEqual(namespace["_rss_mib"](123), 100.0)
        with patch("builtins.open", side_effect=FileNotFoundError):
            self.assertIsNone(namespace["_rss_mib"](123))

    def test_process_pid_lifecycle(self):
        self.assertIn("_a_pid = p.pid", SOURCE)
        self.assertIn("_a_pid = None", SOURCE)


if __name__ == "__main__":
    unittest.main()
