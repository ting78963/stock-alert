import unittest
from research.premarket_crossovers_v1 import classify
class TestCrossovers(unittest.TestCase):
    def test_taiex_golden(self):
        self.assertEqual(classify({"s":101,"l":100},{"s":99,"l":100},"s","l"),"golden_cross")
    def test_twd_appreciation(self):
        self.assertEqual(classify({"s":31,"l":32},{"s":33,"l":32},"s","l",True),"golden_cross")
    def test_twd_depreciation(self):
        self.assertEqual(classify({"s":33,"l":32},{"s":31,"l":32},"s","l",True),"death_cross")
    def test_no_repeated_cross(self):
        self.assertEqual(classify({"s":31,"l":32},{"s":30,"l":32},"s","l",True),"bullish")
    def test_missing(self):
        self.assertEqual(classify({"s":None,"l":32},{"s":30,"l":32},"s","l",True),"unavailable")
