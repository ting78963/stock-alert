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

    def test_regression_ma_fixture(self):
        # Regression fixture; intermediate closes are not independently verified.
        fixture=[42711.92,44257.15,43091.87,43675.12,41040.08,40092.11,40194.91,38426.89,36033.29,36811.89,40122.35]
        # Padding only satisfies MA20 readiness; cannot affect MA5/10 or prior values.
        s=short_term_snapshot([40000.0]*10+fixture)
        self.assertEqual(s["levels"][5]["ma"],38317.87)
        self.assertEqual(s["levels"][10]["ma"],40374.57)
        self.assertEqual(s["levels"][5]["direction"],"↗")
        self.assertEqual(s["levels"][10]["direction"],"↘")
        self.assertTrue(s["levels"][5]["above"])
        self.assertFalse(s["levels"][10]["above"])

    def test_observed_structure_with_hypothetical_open(self):
        # Structure from the 2026-11-24 Render shell MA snapshot.
        # Opening TX and FX changes are hypothetical, not live quotes.
        trend={"weekly":{"structure":"偏多"},"daily":{"structure":"偏空"},
               "short_term":{"label":"站回五日線，十日線仍有壓力",
                             "levels":{5:{"above":True},10:{"above":False}}}}
        values={"sox":{"status":"close","change":"+14.03%"},
                "usdtwd":{"status":"live","change":"+0.0128"}}
        self.assertEqual(market_outlook(trend,values)[0],"今日方向待評估")
        for change,expected in [("+176 (+0.44%)","偏多但仍須觀察"),
                                ("-176 (-0.44%)","多頭結構下的短線回檔"),
                                ("0 (0.00%)","盤前方向中性")]:
            with self.subTest(change=change):
                values["tx"]={"status":"live","change":change}
                title,observation=market_outlook(trend,values)
                self.assertEqual(title,expected)
                self.assertIn("十日線仍有壓力",observation)
