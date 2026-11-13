import unittest
from research.stage_f11_from_f10_v1 import valid

class F11StageTests(unittest.TestCase):
    def test_valid_common_stock(self):
        self.assertTrue(valid("2330", {"symbol":"2330","market":"TSE","securityType":"01","industry":"24"}))
    def test_valid_innovation_stock(self):
        self.assertTrue(valid("2237", {"symbol":"2237","market":"TIB","securityType":"01","industry":"12"}))
    def test_valid_dr(self):
        self.assertTrue(valid("9103", {"symbol":"9103","market":"TSE","securityType":"19","industry":"00"}))
    def test_reject_wrong_identity(self):
        self.assertFalse(valid("2330", {"symbol":"2317","market":"TSE","securityType":"01","industry":"24"}))
    def test_reject_missing_metadata(self):
        self.assertFalse(valid("2330", {"symbol":"2330","market":"TSE","industry":"24"}))
    def test_reject_unknown_security_type(self):
        self.assertFalse(valid("2330", {"symbol":"2330","market":"TSE","securityType":"02","industry":"24"}))
    def test_excluded_industry_is_still_stored(self):
        self.assertTrue(valid("2634", {"symbol":"2634","market":"TSE","securityType":"01","industry":"15"}))

if __name__ == "__main__":
    unittest.main()
