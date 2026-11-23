import unittest
from market_maintenance_flex_v1 import build_market_maintenance_flex

class MarketMaintenanceFlexTests(unittest.TestCase):
    def report(self,ta,fx):
        return build_market_maintenance_flex("2026-11-23",ta,fx)

    def test_both_current_complete(self):
        x=self.report({"status":"updated","latest":"2026-11-23"},{"status":"already_updated","latest":"2026-11-23"})
        self.assertIn("完成",x["altText"])
        self.assertIn("全部完成",x["contents"]["body"]["contents"][2]["text"])

    def test_stale_fx_cannot_claim_success(self):
        x=self.report({"status":"updated","latest":"2026-11-23"},{"status":"not_published","latest":"2026-11-20"})
        self.assertIn("未完成",x["altText"])
        self.assertIn("待補齊",x["contents"]["body"]["contents"][2]["text"])

    def test_missing_taiex_cannot_claim_success(self):
        x=self.report(None,{"status":"updated","latest":"2026-11-23"})
        self.assertIn("未完成",x["altText"])

if __name__=="__main__":
    unittest.main()
