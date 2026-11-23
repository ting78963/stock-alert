# -*- coding: utf-8 -*-
import unittest
from datetime import date,timedelta
from taiex_trend_narrative_v1 import _state, analyze_taiex

class TaiexNarrativeTests(unittest.TestCase):
    def test_insufficient_history_does_not_invent_trend(self):
        self.assertEqual(_state([100.0]*99)["label"],"資料不足")

    def test_golden_cross(self):
        values=[100.0]*102+[110.0]*20
        # Explicit transition from below to above, no guess based on absolute level.
        states=[_state(values[:n]) for n in range(102,len(values)+1)]
        self.assertTrue(any(s["cross"]=="黃金交叉" for s in states))

    def test_bearish_crossover(self):
        values=[100.0]*102+[90.0]*20
        states=[_state(values[:n]) for n in range(102,len(values)+1)]
        self.assertTrue(any(s["cross"]=="死亡交叉" for s in states))

    def test_weekly_uses_completed_weeks(self):
        start=date(2023,1,2)
        rows=[]
        for i in range(160*7):
            d=start+timedelta(days=i)
            if d.weekday()<5:
                rows.append({"date":d.isoformat(),"close":100+i*0.1})
        report=date(2026,1,12)
        first=analyze_taiex(rows,report.isoformat())
        # The latest Monday bar must not alter weekly trend until week completes.
        monday={"date":report.isoformat(),"close":100000}
        # Replace an existing same-date observation rather than introducing a conflict.\n        second=analyze_taiex([r for r in rows if r["date"]!=report.isoformat()]+[monday],report.isoformat())
        self.assertEqual(first["weekly"],second["weekly"])

if __name__=="__main__":
    unittest.main()
