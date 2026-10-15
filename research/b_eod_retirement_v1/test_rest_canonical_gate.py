# -*- coding: utf-8 -*-
import unittest
from rest_canonical_gate import compare_rest_canonical
def bar(t="13:29:00",v=100):
    return dict(date="2026-10-15",stock_id="1476",minute=t,open=10,high=11,low=9,close=10.5,volume=v)
class TestRestCanonical(unittest.TestCase):
    def test_sparse_no_1330_is_valid_comparison(self):
        x=[bar("09:01:00"),bar("13:29:00")]
        self.assertTrue(compare_rest_canonical(x,x,"2026-10-15","1476").ok)
    def test_missing_rest_minute_rejected(self):
        self.assertEqual(compare_rest_canonical([bar()],[bar(),bar("13:30:00")],"2026-10-15","1476").reason,"minute_set_mismatch")
    def test_changed_ohlcv_rejected(self):
        self.assertTrue(compare_rest_canonical([bar(v=101)],[bar(v=100)],"2026-10-15","1476").reason.startswith("ohlcv_mismatch"))
    def test_wrong_day_rejected(self):
        x=bar();x["date"]="2026-10-14"
        self.assertEqual(compare_rest_canonical([x],[bar()],"2026-10-15","1476").reason,"rest_identity")
    def test_duplicate_rejected(self):
        self.assertEqual(compare_rest_canonical([bar(),bar()],[bar()],"2026-10-15","1476").reason,"rest_duplicate")
    def test_empty_rest_rejected(self):
        self.assertEqual(compare_rest_canonical([],[bar()],"2026-10-15","1476").reason,"empty_rest")
    def test_matching_bars_do_not_claim_finality(self):
        x=compare_rest_canonical([bar()],[bar()],"2026-10-15","1476")
        self.assertEqual(x.reason,"bars_match_finality_unproven")
if __name__=="__main__":unittest.main(verbosity=2)
