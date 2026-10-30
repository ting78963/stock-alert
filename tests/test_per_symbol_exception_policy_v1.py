import unittest
from research.per_symbol_exception_policy_v1 import (
    classify_exception, should_scan, check_systemic_health,
    recover, SystemicHistoryFailure,
)

class ExceptionPolicyTests(unittest.TestCase):
    def test_one_bad_stock_only(self):
        bad={"5355"}
        self.assertFalse(should_scan("5355",bad))
        self.assertTrue(should_scan("2330",bad))
    def test_many_bad_stocks(self):
        bad={"5355","8176","2067"}
        self.assertTrue(should_scan("2330",bad))
        self.assertFalse(should_scan("8176",bad))
    def test_404_not_automatically_halt(self):
        item=classify_exception("5355","HTTP 404")
        self.assertEqual(item["state"],"QUARANTINED")
        self.assertNotIn("OFFICIAL",item["state"])
    def test_no_early_recovery(self):
        self.assertFalse(recover("5355",["2026-10-29","2026-10-30"],["2026-10-30"]))
        self.assertTrue(recover("5355",["2026-10-29"],["2026-10-29"]))
    def test_systemic_failure_stops(self):
        self.assertTrue(check_systemic_health(1447,2))
        with self.assertRaises(SystemicHistoryFailure):
            check_systemic_health(1447,300)
        with self.assertRaises(SystemicHistoryFailure):
            check_systemic_health(0,0)

if __name__=="__main__":
    unittest.main()
