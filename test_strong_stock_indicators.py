import unittest
from strong_stock_indicators import calculate, macd

class IndicatorTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(calculate([]), {})

    def test_flat_osc(self):
        self.assertEqual(macd([100.0] * 100)['hist'], 0.0)

if __name__ == '__main__':
    unittest.main()
