import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from vcp_scan_once_adapter import VcpScanOnceRuntime
from vcp_eod_watchlist_v1 import classify,build_flex

class EodTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selector=VcpScanOnceRuntime(lambda:datetime(2026,11,26,17,tzinfo=ZoneInfo("Asia/Taipei"))).engine.selector
    def bars(self, tail=100, volume=100, previous=100):
        prices=[100]+[90,110]*10+[96,104]*10+[99.8,100.2]*9+[previous,tail]
        # The first prior-20 bar belongs to the preceding contraction segment.
        # Keep it below the intended breakout threshold, not at 104.
        prices[-21]=100.2
        return [((datetime(2026,11,26)-timedelta(days=len(prices)-1-i)).date().isoformat(),p,volume if i==len(prices)-1 else 100) for i,p in enumerate(prices)]
    def test_near(self):
        r=classify(self.selector,"2330",self.bars())
        self.assertEqual(r["category"],"near")
        self.assertAlmostEqual(r["threshold"],100.2*1.003)
    def test_first(self):
        r=classify(self.selector,"2330",self.bars(101,150))
        self.assertEqual(r["category"],"first_breakout")
    def test_second(self):
        self.assertIsNone(classify(self.selector,"2330",self.bars(102,150,101)))
    def test_volume(self):
        r=classify(self.selector,"2330",self.bars(101,100))
        self.assertEqual(r["category"],"near")
    def test_short(self):
        self.assertIsNone(classify(self.selector,"2330",self.bars()[-30:]))
    def test_flex(self):
        result=dict(day="2026-11-26",near=[],first_breakout=[],evaluated=1,missing_metadata=0,missing_history=0)
        self.assertEqual(build_flex(result)["type"],"flex")
    def test_zero_matches_is_success(self):
        import json, os
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from vcp_eod_watchlist_v1 import send_once
        result=dict(day="2026-11-26",near=[],first_breakout=[],evaluated=1447,missing_metadata=0,missing_history=0)
        flex=build_flex(result)
        self.assertEqual(json.dumps(flex,ensure_ascii=False).count("無符合股票"),2)
        with TemporaryDirectory() as d, patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test","LINE_TO_ID":"test"}), patch("urllib.request.urlopen") as push:
            push.return_value.__enter__.return_value.status=200
            marker=Path(d)/"sent.json"
            self.assertTrue(send_once(result,marker))
            self.assertTrue(marker.exists())
            self.assertFalse(send_once(result,marker))
            push.assert_called_once()

    def test_market_scale(self):
        import time,tracemalloc
        bars=self.bars()
        tracemalloc.start()
        started=time.monotonic()
        try:
            for i in range(1500):
                row=classify(self.selector,str(1000+i),bars)
                self.assertEqual(row["category"],"near")
            current,peak=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        print(f"EOD 1500 symbols: {time.monotonic()-started:.2f}s, Python allocation peak {peak/1048576:.2f} MiB")
        self.assertLess(peak,10*1048576)

    def test_duplicate_marker(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from vcp_eod_watchlist_v1 import send_once
        with TemporaryDirectory() as d:
            marker=Path(d)/"sent.json"
            marker.write_text('{"sent":true}')
            with patch("urllib.request.urlopen") as push:
                self.assertFalse(send_once({"day":"2026-11-26"},marker))
                push.assert_not_called()

if __name__=="__main__":
    unittest.main()
