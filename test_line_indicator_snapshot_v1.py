"""Read-only indicator snapshot integration tests, no production signal or LINE."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from line_indicator_snapshot_v1 import compute_indicators

class SnapshotTests(unittest.TestCase):
    def test_completed_history_and_partial_today(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "history.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE daily_ohlcv (symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL)")
                from datetime import date, timedelta
                d = date(2026, 5, 4)
                items = []
                for i in range(110):
                    while d.weekday() > 4:
                        d += timedelta(days=1)
                    price = 80 + i * .2
                    items.append(("1301", d.isoformat(), price, price + 1, price - 1, price))
                    d += timedelta(days=1)
                db.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?)", items)
            today = "2026-10-26"
            minutes = [{"date": today, "minute": "09:00:00", "open": 102, "high": 104, "low": 101, "close": 103}]
            result = compute_indicators("1301", today, minutes, "09:00:59", dbpath)
            self.assertIsInstance(result.get("osc"), float)
            self.assertIn("weekly_kd", result)
            self.assertIn("ma_cross_day", result)
            self.assertIn("strong_buy", result)
            self.assertIn("ma20_first_above", result)
            self.assertIsInstance(result["ma20_first_above"], bool)
            self.assertEqual(compute_indicators("1301", today, minutes, "08:59:59", dbpath), {})
            self.assertEqual(compute_indicators("9999", today, minutes, "09:00:59", dbpath), {})

if __name__ == "__main__":
    unittest.main()
