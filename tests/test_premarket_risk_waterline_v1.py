import unittest
from itertools import product
from research.premarket_risk_waterline_v1 import target_for, analyze

class WaterlineTests(unittest.TestCase):
    def test_all_states(self):
        expected = {
            "0000":20,"0001":20,"0010":20,"0011":30,
            "0100":20,"0101":30,"0110":20,"0111":70,
            "1000":20,"1001":20,"1010":20,"1011":30,
            "1100":30,"1101":50,"1110":30,"1111":80,
        }
        for bits in product((False,True),repeat=5):
            key="".join(str(int(b)) for b in bits[:4])
            want=expected[key] if bits[4] else min(30 if bits[0] and bits[1] else 20,expected[key])
            with self.subTest(bits=bits):
                self.assertEqual(target_for(*bits),want)

    def test_short_term_sequence(self):
        states = [(False,False),(True,False),(True,True),(False,True),(True,True)]
        self.assertEqual([target_for(a,b,False,False,False) for a,b in states],
                         [20,20,30,20,30])

    def test_no_5ma_only_recovery(self):
        for a,b,w in product((False,True),repeat=3):
            self.assertEqual(target_for(False,False,a,b,w),
                             target_for(True,False,a,b,w))

    def test_departure_after_touch(self):
        r=analyze([100]*101+[101],90,90,previous_above={5:False,10:False})
        self.assertEqual(r["events"][5],"突破")
        self.assertEqual(r["events"][10],"突破")

    def test_unchanged(self):
        r=analyze(list(range(1,102)),50,49)
        self.assertEqual((r["target"],r["delta"],r["action"]),(80,0,"維持"))

    def test_week_cap(self):
        r=analyze(list(range(1,102)),110,49)
        self.assertEqual((r["target"],r["delta"]),(30,-50))
        r=analyze(list(range(1,102)),50,110)
        self.assertEqual((r["target"],r["delta"]),(80,50))

    def test_missing(self):
        self.assertEqual(analyze([1],None,None,30)["status"],"pending")

class SeasonalBiasTests(unittest.TestCase):
    def test_boundaries(self):
        from research.premarket_risk_waterline_v1 import seasonal_bias
        for price,level in [(107.99,"normal"),(108,"early"),(109.99,"early"),
                            (110,"high"),(113.99,"high"),(114,"extreme"),
                            (90,"normal"),(89.99,"negative")]:
            with self.subTest(price=price):
                closes=[(6000-price)/59]*59+[price]
                self.assertEqual(seasonal_bias(closes)["level"],level)
    def test_missing(self):
        from research.premarket_risk_waterline_v1 import seasonal_bias
        self.assertEqual(seasonal_bias([100]*59)["status"],"pending")
        self.assertEqual(seasonal_bias([100]*59+[0])["status"],"pending")

class SeasonalIntegrationTests(unittest.TestCase):
    def test_independent_warning_and_card(self):
        from datetime import date, timedelta
        from research.premarket_risk_waterline_v1 import analyze_history
        from premarket_market_flex_v1 import trend_section
        import json
        rows=[]
        day=date(2025,1,1)
        while len(rows)<120:
            if day.weekday()<5:
                rows.append({"date":day.isoformat(),"close":100+len(rows)})
            day+=timedelta(days=1)
        result=analyze_history(rows,day)
        self.assertEqual(result["target"],80)
        self.assertEqual(result["seasonal_bias"]["level"],"extreme")
        card=json.dumps(trend_section({"waterline":result}),ensure_ascii=False)
        self.assertIn("極端警戒",card)
        self.assertIn("建議持股 80%",card)
        pending=analyze_history(rows[-60:],day)
        self.assertEqual(pending["status"],"pending")
        self.assertEqual(pending["seasonal_bias"]["status"],"ok")
        self.assertIn("季線乖離率",json.dumps(trend_section({"waterline":pending}),ensure_ascii=False))

class TouchTests(unittest.TestCase):
    def test_touch_preserves_side_and_other_cap(self):
        from research.premarket_risk_waterline_v1 import snapshot
        closes=[200]*95+[98,99,101,102,100]
        for side in (True,False):
            result=snapshot(closes,90,{5:side})
            self.assertIn(5,result["touching"])
            self.assertEqual(result["above"][5],side)
            self.assertEqual(result["caps"][100],30)
            self.assertLessEqual(result["target"],30)
    def test_week_cap_during_daily_touch(self):
        closes=list(range(1,97))+[98,99,101,102,100]
        result=analyze(closes,110,50)
        self.assertEqual(result["target"],30)
        self.assertNotIn(5,result["events"])
        self.assertEqual(result["events"]["week20"],"跌破")
    def test_consecutive_touch_conservative(self):
        result=analyze([100]*101,100,100)
        self.assertEqual(result["target"],20)
        self.assertEqual(result["events"],{})

if __name__=="__main__":
    unittest.main()
