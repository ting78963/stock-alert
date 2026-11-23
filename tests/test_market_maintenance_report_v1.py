import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from market_maintenance_report_v1 import build_from_stores

TPE=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,23,17,10,tzinfo=TPE)

class CombinedReportTests(unittest.TestCase):
    def test_current_both_sufficient(self):
        rows=[{"date":(NOW.date()-timedelta(days=850-i)).isoformat(),"close":100+i} for i in range(850)]
        rows[-1]={"date":"2026-11-23","close":500}
        with patch("market_maintenance_report_v1.read_taiex",return_value=rows),patch("market_maintenance_report_v1.read_fx",return_value=rows):
            card=build_from_stores(NOW)
        self.assertIn("完成",card["altText"])

    def test_stale_fx_blocks_success(self):
        rows=[{"date":(NOW.date()-timedelta(days=850-i)).isoformat(),"close":100+i} for i in range(850)]
        rows[-1]={"date":"2026-11-23","close":500}
        with patch("market_maintenance_report_v1.read_taiex",return_value=rows),patch("market_maintenance_report_v1.read_fx",return_value=rows[:-1]):
            card=build_from_stores(NOW)
        self.assertIn("未完成",card["altText"])

    def test_read_failure_blocks_success(self):
        with patch("market_maintenance_report_v1.read_taiex",side_effect=OSError("disk")),patch("market_maintenance_report_v1.read_fx",return_value=[]):
            card=build_from_stores(NOW)
        self.assertIn("未完成",card["altText"])

if __name__=="__main__":
    unittest.main()
