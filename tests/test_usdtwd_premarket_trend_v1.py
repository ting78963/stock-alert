import unittest
from datetime import date, timedelta
from research.usdtwd_premarket_trend_v1 import fx_premarket_snapshot


class FXPremarketTests(unittest.TestCase):
    def rows(self, closes):
        start = date(2026, 1, 1)
        return [{"date": (start + timedelta(days=i)).isoformat(), "close": v} for i, v in enumerate(closes)]

    def test_ma60_requires_60_bars_and_cross_61(self):
        rows = self.rows([30.0] * 60)
        report = fx_premarket_snapshot(rows, "2026-04-01")
        self.assertEqual(report["ma60"], 30.0)
        self.assertEqual(report["ma20_60"], "insufficient")
        rows = self.rows([30.0] * 60 + [31.0])
        self.assertEqual(fx_premarket_snapshot(rows, "2026-04-01")["ma20_60"], "above")

    def test_premarket_excludes_today(self):
        rows = self.rows([30.0] * 61)
        rows.append({"date": "2026-04-01", "close": 999.0})
        result = fx_premarket_snapshot(rows, "2026-04-01")
        self.assertEqual(result["last_close"], 30.0)
        self.assertEqual(result["count"], 61)

    def test_insufficient_data(self):
        result = fx_premarket_snapshot(self.rows([30.0] * 10), "2026-04-01")
        self.assertIsNone(result["ma60"])
        self.assertEqual(result["ma20_60"], "insufficient")


if __name__ == "__main__":
    unittest.main()
