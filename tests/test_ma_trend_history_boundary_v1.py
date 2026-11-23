import unittest
from research.strong_stock_ma_parity_v1 import ma_trend


class MATrendHistoryBoundaryTests(unittest.TestCase):
    def test_100_bars_has_ma100_value_but_no_direction(self):
        rows = [{"close": 100} for _ in range(100)]
        result = ma_trend(rows, (100,))["ma100"]
        self.assertEqual(result["value"], 100)
        self.assertEqual(result["direction"], "insufficient")

    def test_101_bars_has_direction(self):
        rows = [{"close": 100} for _ in range(100)] + [{"close": 200}]
        result = ma_trend(rows, (100,))["ma100"]
        self.assertEqual(result["direction"], "rising")


if __name__ == "__main__":
    unittest.main()
