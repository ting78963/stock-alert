# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from datetime import date,timedelta
from premarket_taiex_adapter_v1 import load_taiex_trend,build_taiex_preview
from taiex_fugle_store_v1 import write_store

class TaiexPremarketAdapterTests(unittest.TestCase):
    def test_missing_store_shows_insufficient_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"missing.json"
            trend=load_taiex_trend("2026-11-23",path)
            self.assertEqual(trend["headline"],"大盤價格趨勢待確認")
            self.assertIsNone(trend["waterline"]["target"])
            self.assertIsNone(trend["last_close"])
            self.assertEqual(trend["completed_week_count"],0)
            self.assertFalse(trend["weekly_ma100_ready"])
            preview=build_taiex_preview("2026-11-23",path)
            self.assertEqual(preview["type"],"flex")
            self.assertIn("資料不足",json.dumps(preview,ensure_ascii=False))
            self.assertFalse(path.exists())

    def test_asof_excludes_today_and_current_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"history.json"
            start=date(2023,1,2)
            rows=[]
            for i in range(1100):
                day=start+timedelta(days=i)
                if day.weekday()<5:
                    rows.append({"date":day.isoformat(),"close":10000+i})
            report="2026-01-12"
            rows.append({"date":report,"close":999999})
            write_store(path,rows)
            trend=load_taiex_trend(report,path)
            self.assertNotEqual(trend["last_close"],999999)
            self.assertEqual(trend["as_of"],report)
            self.assertEqual(trend["headline"],"大盤偏多")
            self.assertEqual(trend["waterline"]["target"],80)
            self.assertEqual(trend["price_regime"],"偏多")
            self.assertIn("大盤偏多",trend["explanation"])
            self.assertTrue(trend["weekly_ma100_ready"])
            self.assertGreaterEqual(trend["completed_week_count"],102)
            self.assertEqual(trend["weekly"]["structure"],"偏多")
            self.assertEqual(trend["daily"]["structure"],"偏多")

if __name__=="__main__":
    unittest.main()
