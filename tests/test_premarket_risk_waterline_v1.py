import unittest
from itertools import product
from research.premarket_risk_waterline_v1 import target_for, analyze

class WaterlineTests(unittest.TestCase):
    def test_all_states(self):
        expected = {
            "0000":20,"0001":30,"0010":30,"0011":50,
            "0100":30,"0101":50,"0110":30,"0111":70,
            "1000":30,"1001":50,"1010":30,"1011":70,
            "1100":30,"1101":50,"1110":30,"1111":80,
        }
        for bits in product((False,True),repeat=5):
            key="".join(str(int(b)) for b in bits[:4])
            want=expected[key] if bits[4] else min(30,expected[key])
            with self.subTest(bits=bits):
                self.assertEqual(target_for(*bits),want)

    def test_unchanged(self):
        r=analyze(list(range(1,102)),50,49)
        self.assertEqual((r["target"],r["delta"],r["action"]),(80,0,"維持"))

    def test_week_cap(self):
        r=analyze(list(range(1,102)),110,49)
        self.assertEqual((r["target"],r["delta"]),(30,-50))
        r=analyze(list(range(1,102)),50,110)
        self.assertEqual((r["target"],r["delta"]),(80,50))

    def test_missing(self):
        self.assertEqual(analyze([1],None,None,30)["status"],"pending")

class SeasonalBiasTests(unittest.TestCase):
    def test_boundaries(self):
        from research.premarket_risk_waterline_v1 import seasonal_bias
        for price,level in [(107.99,"normal"),(108,"early"),(109.99,"early"),
                            (110,"high"),(113.99,"high"),(114,"extreme"),
                            (90,"normal"),(89.99,"negative")]:
            with self.subTest(price=price):
                closes=[(6000-price)/59]*59+[price]
                self.assertEqual(seasonal_bias(closes)["level"],level)
    def test_missing(self):
        from research.premarket_risk_waterline_v1 import seasonal_bias
        self.assertEqual(seasonal_bias([100]*59)["status"],"pending")
        self.assertEqual(seasonal_bias([100]*59+[0])["status"],"pending")

if __name__=="__main__":
    unittest.main()
