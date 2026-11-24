import unittest
from datetime import date, timedelta
from research.taiex_premarket_ma_v1 import market_trend_snapshot


def weekdays(start, count, values):
    result = []
    day = date.fromisoformat(start)
    while len(result) < count:
        if day.weekday() < 5:
            result.append({"date": day.isoformat(), "close": values[len(result)]})
        day += timedelta(days=1)
    return result, day


class MarketPremarketMATests(unittest.TestCase):
    def test_weekly_ma_uses_calendar_weeks(self):
        rows, end = weekdays("2024-01-01", 530, [100.0] * 530)
        s = market_trend_snapshot(rows, end.isoformat())
        self.assertEqual(s["daily"]["ma"]["ma20"]["direction"], "flat")
        self.assertEqual(s["weekly"]["ma"]["ma20"]["direction"], "flat")
        self.assertGreaterEqual(s["weekly"]["count"], 100)

    def test_weekly_not_ready_without_101_completed_weeks(self):
        rows, end = weekdays("2024-01-01", 480, [100.0] * 480)
        s = market_trend_snapshot(rows, end.isoformat())
        self.assertEqual(s["weekly"]["cross_20_100"]["status"], "insufficient")

    def test_weekly_golden_cross_uses_same_algorithm(self):
        # 102 complete weeks: 20MA starts below 100MA, then crosses on final week.
        values = [110.0] * (81 * 5) + [100.0] * (20 * 5) + [300.0] * 5
        rows, end = weekdays("2024-01-01", len(values), values)
        s = market_trend_snapshot(rows, end.isoformat())
        self.assertEqual(s["weekly"]["cross_20_100"]["status"], "golden_cross")
        self.assertEqual(s["weekly"]["ma"]["ma20"]["direction"], "rising")

    def test_weekly_bearish_cross_uses_same_algorithm(self):
        values = [100.0] * (81 * 5) + [102.0] * (20 * 5) + [1.0] * 5
        rows, end = weekdays("2024-01-01", len(values), values)
        s = market_trend_snapshot(rows, end.isoformat())
        self.assertEqual(s["weekly"]["cross_20_100"]["status"], "death_cross")
        self.assertEqual(s["weekly"]["ma"]["ma20"]["direction"], "falling")

    def test_premarket_does_not_include_report_day(self):
        rows, _ = weekdays("2024-01-01", 530, [100.0] * 529 + [200.0])
        as_of = rows[-1]["date"]
        s = market_trend_snapshot(rows, as_of)
        self.assertEqual(s["daily"]["count"], 529)
        self.assertEqual(s["daily"]["ma"]["ma20"]["direction"], "flat")


if __name__ == "__main__":
    unittest.main()
