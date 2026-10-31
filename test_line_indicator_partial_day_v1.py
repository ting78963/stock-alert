"""Isolated checks for causal partial-day aggregation. No network or LINE."""
import unittest
from line_indicator_partial_day_v1 import partial_daily_candle, append_partial_day

DAY = "2026-10-26"

def bar(t, o, h, l, c, day=DAY):
    return {"date": day, "minute": t, "open": o, "high": h, "low": l, "close": c}

class PartialDayTests(unittest.TestCase):
    def test_aggregation_uses_ordered_completed_minutes(self):
        rows = [bar("09:02:00", 12, 13, 11, 12.5),
                bar("09:00:00", 10, 11, 9, 10.5),
                bar("09:01:00", 10.5, 12, 10, 12)]
        self.assertEqual(partial_daily_candle(rows, DAY, "09:02:59"),
                         {"date": DAY, "open": 10, "high": 13, "low": 9, "close": 12.5})
    def test_future_and_duplicate_bars_blocked(self):
        rows = [bar("09:00:00", 10, 11, 9, 10),
                bar("09:02:00", 10, 12, 9, 11)]
        self.assertIsNone(partial_daily_candle(rows, DAY, "09:01:59"))
        self.assertIsNone(partial_daily_candle([rows[0], rows[0]], DAY))
    def test_bad_prices_and_mixed_dates_blocked(self):
        self.assertIsNone(partial_daily_candle([bar("09:00:00", 10, 9, 8, 10)], DAY))
        self.assertIsNone(partial_daily_candle([bar("09:00:00", 10, 11, 9, 10, "2026-10-23")], DAY))
    def test_never_double_counts_today(self):
        rows = [bar("09:00:00", 10, 11, 9, 10)]
        self.assertIsNone(append_partial_day([{"date": DAY, "close": 10}], rows, DAY))
        self.assertEqual(len(append_partial_day([{"date": "2026-10-22", "close": 9}], rows, DAY)), 2)

if __name__ == "__main__":
    unittest.main()
