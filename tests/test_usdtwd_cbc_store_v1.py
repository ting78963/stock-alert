import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from usdtwd_cbc_store_v1 import read_store,update

class CBCCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"cbc.json"
        self.rows=[{"date":f"2026-10-{d:02d}","close":32+d/100} for d in range(1,21)]

    def test_store_and_read(self):
        with patch("usdtwd_cbc_store_v1.fetch_daily",return_value=self.rows):
            result=update(as_of="2026-11-23",path=self.path)
        self.assertEqual(result["stored"],20)
        self.assertEqual(len(read_store(self.path)),20)
        self.assertIsNotNone(result["snapshot"]["daily_ma5"])
        self.assertIsNotNone(result["snapshot"]["daily_ma20"])
        self.assertNotIn("weekly_ma100",result["snapshot"])

    def test_failed_download_preserves_cache(self):
        with patch("usdtwd_cbc_store_v1.fetch_daily",return_value=self.rows):
            update(as_of="2026-11-23",path=self.path)
        before=self.path.read_bytes()
        with patch("usdtwd_cbc_store_v1.fetch_daily",side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                update(as_of="2026-11-23",path=self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_regression_preserves_cache(self):
        with patch("usdtwd_cbc_store_v1.fetch_daily",return_value=self.rows):
            update(as_of="2026-11-23",path=self.path)
        before=self.path.read_bytes()
        with patch("usdtwd_cbc_store_v1.fetch_daily",return_value=self.rows[:-1]):
            with self.assertRaises(ValueError):
                update(as_of="2026-11-23",path=self.path)
        self.assertEqual(self.path.read_bytes(),before)

if __name__=="__main__":
    unittest.main()
