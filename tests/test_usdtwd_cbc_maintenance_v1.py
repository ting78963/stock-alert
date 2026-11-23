import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from usdtwd_cbc_maintenance_v1 import maintain_cbc_once

TPE=ZoneInfo("Asia/Taipei")

class CBCMaintenanceTests(unittest.TestCase):
    def at(self,h,m=0,day=23):
        return datetime(2026,11,day,h,m,tzinfo=TPE)

    def test_before_window(self):
        self.assertEqual(maintain_cbc_once(self.at(16,59)),"not_due")

    def test_after_window(self):
        self.assertEqual(maintain_cbc_once(self.at(18)),"window_closed")

    def test_weekend(self):
        self.assertEqual(maintain_cbc_once(self.at(17,day=22)),"weekend")

    @patch("usdtwd_cbc_maintenance_v1.update")
    @patch("usdtwd_cbc_maintenance_v1.read_store",return_value=[{"date":"2026-11-23","close":32.9}])
    def test_cached_today(self,read,update):
        self.assertEqual(maintain_cbc_once(self.at(17)),"already_updated")
        update.assert_not_called()

    @patch("usdtwd_cbc_maintenance_v1.update",return_value={"latest":"2026-11-20"})
    @patch("usdtwd_cbc_maintenance_v1.read_store",return_value=[])
    def test_not_published(self,read,update):
        self.assertEqual(maintain_cbc_once(self.at(17)),"not_published")

    @patch("usdtwd_cbc_maintenance_v1.update",return_value={"latest":"2026-11-23"})
    @patch("usdtwd_cbc_maintenance_v1.read_store",return_value=[])
    def test_published(self,read,update):
        self.assertEqual(maintain_cbc_once(self.at(17)),"updated")

if __name__=="__main__":
    unittest.main()
