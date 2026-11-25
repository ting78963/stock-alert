import unittest
from datetime import datetime
from research.premarket_sox_quote_adapter_v1 import fetch_sox_quote
from premarket_quote_policy_v1 import validate_quote

class SoxAdapterTest(unittest.TestCase):
    def test_valid_and_stale(self):
        now=datetime.fromisoformat("2026-11-24T08:55:00+08:00")
        row=dict(available=True,source="yahoo_chart_sox",close_date="2026-11-23",close=101,previous_close=100)
        quote=fetch_sox_quote(now,lambda:row)
        self.assertEqual(quote["change"],"+1.00 (+1.00%)")
        self.assertEqual(quote["previous_close"],"100.00")
        self.assertEqual(validate_quote("sox",quote,now)["previous_close"],"100.00")
        self.assertEqual(validate_quote("sox",quote,now)["status"],"close")
        row["close_date"]="2026-11-16"
        self.assertIsNone(fetch_sox_quote(now,lambda:row))
        row["close_date"]="2026-11-25"
        self.assertIsNone(fetch_sox_quote(now,lambda:row))
