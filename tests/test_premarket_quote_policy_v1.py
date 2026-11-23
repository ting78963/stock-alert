import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from premarket_quote_policy_v1 import validate_quote
TPE=ZoneInfo("Asia/Taipei")
REPORT=datetime(2026,11,23,8,55,tzinfo=TPE)

class QuotePolicyTests(unittest.TestCase):
    def test_tx_live_quote_within_three_minutes(self):
        q=validate_quote("tx",{"value":"28,000","quoted_at":"2026-11-23T08:54:00+08:00","session":"day"},REPORT)
        self.assertEqual(q["status"],"live")
        self.assertEqual(q["value"],"28,000")
    def test_fx_old_quote_is_not_presented_as_live(self):
        q=validate_quote("usdtwd",{"value":"31.20","quoted_at":"2026-11-23T08:45:00+08:00"},REPORT)
        self.assertEqual(q["status"],"stale")
        self.assertIsNone(q["value"])
    def test_sox_prior_session_close_is_allowed(self):
        q=validate_quote("sox",{"value":"6,000","quoted_at":"2026-11-20T16:00:00-05:00","source":"nasdaq"},REPORT)
        self.assertEqual(q["status"],"close")
    def test_missing_timestamp_fails_closed(self):
        q=validate_quote("tx",{"value":"28,000"},REPORT)
        self.assertEqual(q["status"],"invalid_time")
        self.assertIsNone(q["value"])
    def test_future_timestamp_is_rejected(self):
        q=validate_quote("tx",{"value":"28,000","quoted_at":"2026-11-23T09:00:00+08:00"},REPORT)
        self.assertEqual(q["status"],"future")
    def test_live_tx_requires_day_session(self):
        q=validate_quote("tx",{"value":"28,000","quoted_at":"2026-11-23T08:54:00+08:00","session":"night"},REPORT)
        self.assertEqual(q["status"],"invalid_session")
    def test_fx_requires_market_or_bank_quote_type(self):
        q=validate_quote("usdtwd",{"value":"32.9","quoted_at":"2026-11-23T08:54:00+08:00"},REPORT)
        self.assertEqual(q["status"],"invalid_kind")
    def test_sox_requires_identified_nasdaq_source(self):
        q=validate_quote("sox",{"value":"6,000","quoted_at":"2026-11-20T16:00:00-05:00"},REPORT)
        self.assertEqual(q["status"],"invalid_source")
    def test_unknown_key_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_quote("other",{},REPORT)

if __name__=="__main__":
    unittest.main()
