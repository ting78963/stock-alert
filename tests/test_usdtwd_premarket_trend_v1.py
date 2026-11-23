import unittest
from datetime import date, timedelta
from research.usdtwd_premarket_trend_v1 import fx_premarket_snapshot


class FXPremarketTests(unittest.TestCase):
    def rows(self, closes):
        start = date(2026, 1, 1)
        return [{"date": (start + timedelta(days=i)).isoformat(), "close": v} for i, v in enumerate(closes)]

    def test_ma20_direction_requires_21_bars(self):
        rows = self.rows([30.0] * 20)
        report = fx_premarket_snapshot(rows, "2026-04-01")
        self.assertEqual(report["ma20"], 30.0)
        self.assertEqual(report["ma20_direction"], "insufficient")
        rows = self.rows([30.0] * 20 + [31.0])
        self.assertEqual(fx_premarket_snapshot(rows, "2026-04-01")["ma20_direction"], "rising")

    def test_usdtwd_rising_means_twd_weakening(self):
        result = fx_premarket_snapshot(self.rows([30.0] * 20 + [31.0]), "2026-04-01")
        self.assertEqual(result["ma5_direction"], "rising")
        self.assertEqual(result["twd_ma5_direction"], "TWD_weakening")

    def test_death_cross_means_twd_strengthening(self):
        result = fx_premarket_snapshot(self.rows([30.0] * 15 + [31.0] * 6 + [29.0]), "2026-04-01")
        self.assertEqual(result["ma5_20"], "death_cross")
        self.assertEqual(result["twd_ma5_20_interpretation"], "TWD_strengthening")

    def test_premarket_excludes_today(self):
        rows = self.rows([30.0] * 61)
        rows.append({"date": "2026-04-01", "close": 999.0})
        result = fx_premarket_snapshot(rows, "2026-04-01")
        self.assertEqual(result["last_close"], 30.0)
        self.assertEqual(result["count"], 61)

    def test_insufficient_data(self):
        result = fx_premarket_snapshot(self.rows([30.0] * 10), "2026-04-01")
        self.assertIsNone(result["ma20"])
        self.assertEqual(result["ma5_20"], "insufficient")


if __name__ == "__main__":
    unittest.main()
