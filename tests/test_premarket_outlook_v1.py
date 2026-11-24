import unittest
from taiex_trend_narrative_v1 import short_term_snapshot
from premarket_taiex_adapter_v1 import market_outlook

class OutlookTests(unittest.TestCase):
    def test_ma(self):
        s=short_term_snapshot(list(range(100,121)))
        self.assertEqual(s["levels"][5]["ma"],118)
        self.assertEqual(s["levels"][10]["ma"],115.5)
        self.assertEqual(s["levels"][20]["ma"],110.5)
        self.assertEqual(s["levels"][5]["direction"],"↗")
        self.assertEqual(s["label"],"短線偏多")
    def test_insufficient(self):
        self.assertFalse(short_term_snapshot([100]*20)["levels"])
    def test_outlook(self):
        for structure,tx,sox,fx,expected in [
            ("偏多",1,1,-1,"多頭共振"),
            ("偏多",-1,-1,1,"多頭結構下的短線回檔"),
            ("偏空",1,1,-1,"空頭結構下的短線反彈"),
            ("偏空",-1,-1,1,"空頭共振"),
            ("偏多",1,-1,1,"偏多但仍須觀察"),
        ]:
            with self.subTest(expected=expected):
                trend={"weekly":{"structure":structure},"daily":{"structure":structure}}
                values={k:{"status":"close" if k=="sox" else "live","change":f"{v:+.2f}%"} for k,v in zip(("tx","sox","usdtwd"),(tx,sox,fx))}
                self.assertEqual(market_outlook(trend,values)[0],expected)
    def test_missing_tx(self):
        self.assertEqual(market_outlook({}, {})[0],"今日方向待評估")
