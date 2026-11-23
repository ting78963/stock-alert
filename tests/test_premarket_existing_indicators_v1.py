import unittest
from research.premarket_existing_indicators_v1 import read_premarket_indicators

class TestExistingIndicators(unittest.TestCase):
    def test_reuses_local_stores_without_network(self):
        ta=[{"date":f"2026-10-{d:02d}","close":10000+d} for d in range(1,31)]
        fx=[{"date":f"2026-10-{d:02d}","close":30+d/100} for d in range(1,31)]
        result=read_premarket_indicators("2026-11-24",lambda:ta,lambda:fx)
        self.assertIsNotNone(result["taiex"]["daily_ma20"])
        self.assertIsNotNone(result["usdtwd"]["daily_ma20"])
    def test_store_error_is_isolated(self):
        def fail():raise OSError("missing store")
        result=read_premarket_indicators("2026-11-24",fail,lambda:[])
        self.assertIsNone(result["taiex"])
        self.assertIsNotNone(result["usdtwd"])

if __name__=="__main__":unittest.main()
