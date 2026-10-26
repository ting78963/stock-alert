"""Regression tests for isolated LINE indicator calculations. No DB, network or LINE."""
import unittest
from datetime import date,timedelta
from line_indicator_calculations_v1 import macd,ma_cross_day,ma_prepare,kd,weekly_kd_label,strong_buy,js_round

def rows(closes,start=date(2026,1,5)):
    out=[]
    day=start
    for c in closes:
        while day.weekday()>=5:day+=timedelta(days=1)
        out.append({"date":day.isoformat(),"open":c,"high":c+2,"low":c-2,"close":c})
        day+=timedelta(days=1)
    return out

class TestIndicators(unittest.TestCase):
    def test_short_history_never_invents_labels(self):
        r=rows([100]*20)
        self.assertIsNone(ma_cross_day(r))
        self.assertFalse(ma_prepare(r))
        self.assertIsNone(weekly_kd_label(r))
        self.assertIsNone(macd([x["close"] for x in r])["hist"])
        self.assertFalse(strong_buy(r))

    def test_constant_macd_zero(self):
        result=macd([100]*70)
        self.assertEqual(result["hist"],0)
        self.assertEqual(result["prev_hist"],0)
        self.assertEqual(result["histArr"],[0,0,0])
        self.assertEqual(result["histArr5"],[0]*5)

    def test_js_round_positive_ties(self):
        self.assertEqual(js_round(1.235,2),1.24)
        self.assertEqual(js_round(-1.235,2),-1.24)

    def test_ma_cross_day_one_and_two(self):
        c=[100]*30+[120]
        self.assertEqual(ma_cross_day(rows(c)),1)
        self.assertEqual(ma_cross_day(rows(c+[120])),2)

    def test_ma_prepare(self):
        c=[100]*25+[99]*3+[99.5,99.8]
        self.assertIsInstance(ma_prepare(rows(c)),bool)

    def test_weekly_kd_has_no_label_on_flat_data(self):
        self.assertIsNone(weekly_kd_label(rows([100]*100)))

    def test_macd_does_not_mutate_closes(self):
        c=[100+i*.25 for i in range(80)]
        original=c[:]
        macd(c)
        self.assertEqual(c,original)

if __name__=="__main__":
    unittest.main()
