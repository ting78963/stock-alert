import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from market_data_maintenance_v1 import maintain_taiex_once

TPE=ZoneInfo("Asia/Taipei")

class MarketBackfillSafetyTests(unittest.TestCase):
    def test_no_api_during_open(self):
        with patch("taiex_fugle_store_v1.update") as update:
            self.assertEqual(maintain_taiex_once(datetime(2026,11,24,10,0,tzinfo=TPE)),"not_due")
            update.assert_not_called()

    def test_one_chunk_per_close_attempt(self):
        with patch("twse_session_gate_v1.is_scheduled_open",return_value=True), patch("taiex_fugle_store_v1.read_store",return_value=[]), patch("taiex_fugle_store_v1.update",return_value={"latest":"2026-11-20","stored":100,"snapshot":{"weekly_ma100":None,"daily_ma100":100}}) as update:
            self.assertEqual(maintain_taiex_once(datetime(2026,11,24,14,35,tzinfo=TPE)),"bootstrapping")
            self.assertEqual(update.call_args.kwargs["max_chunks"],1)

    def test_late_bootstrap_allowed(self):
        with patch("twse_session_gate_v1.is_scheduled_open",return_value=True), patch("taiex_fugle_store_v1.read_store",return_value=[]), patch("taiex_fugle_store_v1.update",return_value={"latest":"2026-11-24","stored":500,"snapshot":{"weekly_ma100":123,"daily_ma100":123}}):
            self.assertEqual(maintain_taiex_once(datetime(2026,11,24,18,10,tzinfo=TPE)),"updated")

if __name__=="__main__":
    unittest.main()
