import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from market_bootstrap_once_v1 import safe_to_bootstrap, bootstrap_once

TPE=ZoneInfo("Asia/Taipei")
class ImmediateBootstrapTests(unittest.TestCase):
    def test_off_hours_and_market_hours(self):
        self.assertTrue(safe_to_bootstrap(datetime(2026,11,23,22,0,tzinfo=TPE)))
        self.assertTrue(safe_to_bootstrap(datetime(2026,11,24,7,0,tzinfo=TPE)))
        self.assertFalse(safe_to_bootstrap(datetime(2026,11,24,9,0,tzinfo=TPE)))
        self.assertFalse(safe_to_bootstrap(datetime(2026,11,24,14,30,tzinfo=TPE)))
    def test_never_fetch_in_trading_window(self):
        with patch("taiex_fugle_store_v1.update") as fetch:
            self.assertEqual(bootstrap_once(datetime(2026,11,24,10,0,tzinfo=TPE)),"market_hours")
            fetch.assert_not_called()
    def test_ma100_ready_but_old_history_must_continue(self):
        now=datetime(2026,11,23,22,55,tzinfo=TPE)
        state={"weekly_ma100":100,"daily_ma100":100}
        with patch("taiex_fugle_store_v1.read_store",return_value=[]),patch("taiex_fugle_store_v1.update",return_value={"stored":478,"latest":"2026-11-06","snapshot":state}) as fetch,patch("usdtwd_cbc_store_v1.read_store",return_value=[{"date":"2026-11-23","close":32}]*20):
            self.assertEqual(bootstrap_once(now),"progress")
            self.assertEqual(fetch.call_args.kwargs["max_chunks"],1)
    def test_bounded_history_and_fx(self):
        now=datetime(2026,11,23,22,55,tzinfo=TPE)
        state={"weekly_ma100":None,"daily_ma100":None}
        with patch("taiex_fugle_store_v1.read_store",return_value=[]),patch("taiex_fugle_store_v1.update",return_value={"stored":200,"latest":"2026-11-20","snapshot":state}) as fetch,patch("usdtwd_cbc_store_v1.read_store",return_value=[]),patch("usdtwd_cbc_store_v1.update",return_value={"stored":4600,"latest":"2026-11-23"}):
            self.assertEqual(bootstrap_once(now),"progress")
            self.assertEqual(fetch.call_args.kwargs["max_chunks"],1)
if __name__=="__main__":
    unittest.main()
