import unittest
from datetime import date,timedelta
from market_history_retention_v1 import retain_taiex,retain_fx
from taiex_market_history_v1 import snapshot,completed_week_closes
from usdtwd_cbc_daily_v1 import trend_snapshot

class TestRetention(unittest.TestCase):
    def test_taiex_preserves_ma_and_previous_week(self):
        start=date(2023,1,2)
        rows=[{"date":(start+timedelta(days=i)).isoformat(),"close":10000+i} for i in range(140*7+3) if i%7<5 and i//7!=50]
        day=start+timedelta(weeks=140,days=3)
        kept=retain_taiex(rows,day)
        self.assertEqual(len(completed_week_closes(kept,day)),105)
        for as_of in (day,day-timedelta(weeks=1)):
            a,b=snapshot(rows,as_of),snapshot(kept,as_of)
            for key in ("daily_ma20","daily_ma100","weekly_ma20","weekly_ma100","last_close"):
                self.assertEqual(a[key],b[key])
    def test_fx_preserves_current_and_previous_ma(self):
        start=date(2026,1,1)
        rows=[{"date":(start+timedelta(days=i)).isoformat(),"close":30+i/100} for i in range(60)]
        kept=retain_fx(rows)
        self.assertEqual(len(kept),25)
        for day in (start+timedelta(days=60),start+timedelta(days=59)):
            a,b=trend_snapshot(rows,day),trend_snapshot(kept,day)
            for key in ("daily_ma5","daily_ma20","direction","last_close"):
                self.assertEqual(a[key],b[key])
    def test_short_history_never_trimmed(self):
        rows=[{"date":"2026-11-23","close":100}]
        self.assertEqual(retain_taiex(rows,"2026-11-24"),rows)
        self.assertEqual(retain_fx(rows),rows)

if __name__=="__main__":unittest.main()
