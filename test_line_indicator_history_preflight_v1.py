"""Regression: today's unfinished daily candle must never enter historical indicator preflight."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research.line_indicator_history_preflight_v1 import audit

class HistoryPreflightTests(unittest.TestCase):
    def test_excludes_asof_day_and_requires_prior_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE daily_ohlcv (symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL)")
                db.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?)", [
                    ("1301", "2026-10-22", 10, 11, 9, 10),
                    ("1301", "2026-10-26", 100, 110, 90, 100),
                ])
            ok = audit(path, "1301", "2026-10-26", min_days=1)
            self.assertEqual(ok["status"], "PASS")
            self.assertEqual(ok["last_day"], "2026-10-22")
            blocked = audit(path, "1301", "2026-10-26", min_days=2)
            self.assertEqual(blocked["status"], "BLOCKED")
            self.assertEqual(blocked["reason"], "INSUFFICIENT_DAYS")

if __name__ == "__main__":
    unittest.main()
