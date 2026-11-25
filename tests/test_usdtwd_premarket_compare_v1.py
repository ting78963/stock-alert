import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from usdtwd_premarket_compare_v1 import compare_to_previous_close,compare_live_to_cbc_close

NOW=datetime(2026,11,23,8,55,tzinfo=ZoneInfo("Asia/Taipei"))
def quote(price,at="2026-11-23T08:54:00+08:00",source="twelve_data"):
    return {"value":price,"quoted_at":at,"quote_kind":"market_spot","source":source}
def close(price,source="twelve_data"):
    return {"value":price,"quote_kind":"market_spot","source":source}

class PremarketFXComparisonTests(unittest.TestCase):
    def test_live_vs_cbc_previous_published_close(self):
        rows=[{"date":"2026-11-20","close":31.5},{"date":"2026-11-23","close":31.9}]
        r=compare_live_to_cbc_close(quote(31.45,source="live_rates"),rows,NOW)
        self.assertEqual(r["status"],"ok")
        self.assertEqual(r["direction"],"TWD_appreciation")
        self.assertEqual(r["previous_close_date"],"2026-11-20")
        self.assertEqual(r["comparison_kind"],"indicative_cross_source")
        self.assertAlmostEqual(r["usd_twd_change_percent"],-0.1587)
    def test_live_vs_cbc_missing_baseline(self):
        r=compare_live_to_cbc_close(quote(31.45,source="live_rates"),[],NOW)
        self.assertEqual(r["status"],"missing_baseline")
    def test_live_vs_cbc_stale_rejected(self):
        r=compare_live_to_cbc_close(quote(31.45,"2026-11-23T08:45:00+08:00",source="live_rates"),[{"date":"2026-11-20","close":31.5}],NOW)
        self.assertEqual(r["status"],"stale")
    def test_live_vs_cbc_reject_other_source(self):
        r=compare_live_to_cbc_close(quote(31.45),[{"date":"2026-11-20","close":31.5}],NOW)
        self.assertEqual(r["status"],"unsupported_live_source")
    def test_depreciation(self):
        r=compare_to_previous_close(quote(31.6),close(31.5),NOW)
        self.assertEqual(r["direction"],"TWD_depreciation")
        self.assertAlmostEqual(r["usd_twd_change_percent"],0.3175)
    def test_appreciation(self):
        r=compare_to_previous_close(quote(31.4),close(31.5),NOW)
        self.assertEqual(r["direction"],"TWD_appreciation")
    def test_stale_quote_rejected(self):
        r=compare_to_previous_close(quote(31.6,"2026-11-23T08:45:00+08:00"),close(31.5),NOW)
        self.assertEqual(r["status"],"stale")
    def test_mismatched_official_close_rejected(self):
        r=compare_to_previous_close(quote(31.6),{"value":31.5,"source":"cbc_interbank_daily_close","quote_kind":"official_daily_close"},NOW)
        self.assertEqual(r["status"],"incomparable_baseline")
    def test_missing_close_rejected(self):
        self.assertEqual(compare_to_previous_close(quote(31.6),None,NOW)["status"],"missing_baseline")

if __name__=="__main__":
    unittest.main()
