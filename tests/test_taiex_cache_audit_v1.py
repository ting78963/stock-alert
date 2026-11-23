# -*- coding: utf-8 -*-
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from taiex_cache_audit_v1 import audit
from taiex_fugle_store_v1 import write_store

class TaiexCacheAuditTests(unittest.TestCase):
    def test_missing_cache_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"missing.json"
            result=audit("2026-11-23",path)
            self.assertFalse(result["cache_exists"])
            self.assertFalse(result["weekly_ma100_ready"])
            self.assertEqual(result["warning"],"歷史資料不足")
            self.assertFalse(path.exists())

    def test_full_history_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cache.json"
            start=date(2023,1,2)
            rows=[]
            for i in range(1100):
                d=start+timedelta(days=i)
                if d.weekday()<5:
                    rows.append({"date":d.isoformat(),"close":10000+i})
            write_store(path,rows)
            result=audit("2026-01-12",path)
            self.assertTrue(result["daily_ma100_ready"])
            self.assertTrue(result["weekly_ma100_ready"])
            self.assertGreaterEqual(result["completed_week_count"],102)
            self.assertIsNone(result["warning"])

    def test_old_cache_warns_without_fabricating_current_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cache.json"
            start=date(2023,1,2)
            rows=[]
            for i in range(850):
                d=start+timedelta(days=i)
                if d.weekday()<5:
                    rows.append({"date":d.isoformat(),"close":10000+i})
            write_store(path,rows)
            result=audit("2026-11-23",path)
            self.assertTrue(result["weekly_ma100_ready"])
            self.assertIn("停更",result["warning"])
            self.assertGreater(result["last_close_age_calendar_days"],14)

if __name__=="__main__":
    unittest.main()
