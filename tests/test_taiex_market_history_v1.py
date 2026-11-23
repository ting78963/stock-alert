import unittest
from datetime import date, timedelta
from taiex_market_history_v1 import normalize_daily, snapshot


class TAIEXHistoryTest(unittest.TestCase):
    def test_order_and_duplicate(self):
        self.assertEqual(normalize_daily([{"date":"2026-11-19","close":10},{"date":"2026-11-18","close":9},{"date":"2026-11-19","close":10}]), [{"date":"2026-11-18","close":9.0},{"date":"2026-11-19","close":10.0}])

    def test_conflict(self):
        with self.assertRaises(ValueError):
            normalize_daily([{"date":"2026-11-19","close":10},{"date":"2026-11-19","close":11}])

    def test_missing_history_is_unknown(self):
        x = snapshot([{"date":"2026-11-20","close":100}], "2026-11-23")
        self.assertIsNone(x["daily_ma20"])
        self.assertIsNone(x["weekly_ma100"])

    def test_current_week_not_used(self):
        rows = [{"date":(date(2026, 11, 2) + timedelta(days=i)).isoformat(),"close":float(i+1)} for i in range(19)]
        x = snapshot(rows, "2026-11-20")
        self.assertEqual(x["completed_week_count"],2)
        self.assertIsNone(x["daily_ma20"])

    def test_ma_with_sufficient_history(self):
        start = date(2024, 1, 1)
        rows = [{"date":(start+timedelta(days=i)).isoformat(),"close":100.0} for i in range(800) if (start+timedelta(days=i)).weekday()<5]
        x = snapshot(rows, "2026-03-15")
        self.assertEqual(x["daily_ma100"],100.0)
        self.assertEqual(x["weekly_ma100"],100.0)


if __name__ == "__main__":
    unittest.main()
