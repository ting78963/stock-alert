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
if __name__=="__main__":
    unittest.main()
