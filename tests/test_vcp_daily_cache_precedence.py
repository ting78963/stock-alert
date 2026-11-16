"""Read-only regression tests for VCP daily-cache precedence.

Run: python -m unittest discover -s tests -p 'test_vcp_daily_cache_precedence.py'
No Render, network, or production data needed.
"""
import ast
import pathlib
import types
import unittest
from datetime import date, timedelta
from typing import Optional, List, Dict, Tuple

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "fugle_a_scanner_v2_4.py"


def load_method():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "FugleAdapter")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "daily_history_local_ready")
    fn.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    ns = {"date": date, "timedelta": timedelta, "Optional": Optional,
          "List": List, "Dict": Dict, "Tuple": Tuple,
          "DailyBar": type("DailyBar", (), {})}
    exec(compile(module, str(SOURCE), "exec"), ns)
    return ns["daily_history_local_ready"]


class CachePrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.read = load_method()
        self.obj = types.SimpleNamespace(daily_cache={}, history_cache={})
        self.calls = []
        def shared(symbol, snapshot):
            self.calls.append((symbol, snapshot))
            return list(range(107))
        self.obj._shared_daily_history = shared

    def test_no_cache_uses_shared_history(self):
        result = self.read(self.obj, "3714", "2026-11-16")
        self.assertEqual(len(result), 107)
        self.assertEqual(len(self.calls), 1)

    def test_stale_short_cache_blocks_recovered_shared_history(self):
        self.obj.daily_cache["3714"] = ("3714|2026-11-16", list(range(48)))
        result = self.read(self.obj, "3714", "2026-11-16")
        # Documents the current risky behavior; change expected behavior
        # in a separate fix after the cause is confirmed.
        self.assertEqual(len(result), 48)
        self.assertEqual(len(self.calls), 0)


if __name__ == "__main__":
    unittest.main()
