import unittest
from research.strong_stock_ma_parity_v1 import daily_ma_cross, daily_ma_values


def rows(values):
    return [{"close": v} for v in values]


class StrongStockMAParityTests(unittest.TestCase):
    def test_insufficient(self):
        self.assertEqual(daily_ma_cross(rows([100] * 100), 100), "")
        self.assertIsNone(daily_ma_values(rows([100] * 19))["ma20"])

    def test_flat(self):
        self.assertEqual(daily_ma_cross(rows([100] * 110), 100), "")

    def test_cross_day1(self):
        values = [110] * 81 + [100] * 20 + [300]
        self.assertEqual(daily_ma_cross(rows(values), 100), "golden_cross")

    def test_cross_day2(self):
        values = [110] * 81 + [100] * 20 + [300, 300]
        self.assertEqual(daily_ma_cross(rows(values), 100), "golden_cross_day2")

    def test_cross_day5(self):
        values = [110] * 81 + [100] * 20 + [300] * 5
        self.assertEqual(daily_ma_cross(rows(values), 100), "golden_cross_day5")

    def test_cross_day6_expired(self):
        values = [110] * 81 + [100] * 20 + [300] * 6
        self.assertEqual(daily_ma_cross(rows(values), 100), "")

    def test_both_periods(self):
        values = [110] * 81 + [100] * 20 + [300]
        for n in (60, 100):
            self.assertEqual(daily_ma_cross(rows(values), n), "golden_cross")


if __name__ == "__main__":
    unittest.main()
