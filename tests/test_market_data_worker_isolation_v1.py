import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import market_data_worker_v1 as worker

class MarketWorkerIsolation(unittest.TestCase):
    def test_taiex_failure_does_not_block_cbc(self):
        now=datetime(2026,11,23,17,5,tzinfo=ZoneInfo("Asia/Taipei"))
        with patch.object(worker,"maintain_taiex_once",side_effect=RuntimeError("test")),patch.object(worker,"maintain_cbc_once",return_value="updated") as fx:
            result=worker.tick(now)
        self.assertEqual(result,{"TAIEX":"error","CBC":"updated"})
        fx.assert_called_once_with(now)
    def test_no_f15_worker_imports(self):
        from pathlib import Path
        src=Path(worker.__file__).read_text(encoding="utf-8")
        self.assertNotIn("f15_",src.lower())
        self.assertNotIn("production_worker",src)

if __name__=="__main__":
    unittest.main()
