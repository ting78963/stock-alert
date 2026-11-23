"""Offline bootstrap regression: never mark a missing latest candle as covered."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from taiex_fugle_store_v1 import update, read_store

class TaiexBootstrapRegression(unittest.TestCase):
    def test_checkpoint_resume_and_missing_current_candle(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"taiex.json"
            day=date(2026,11,23)
            calls=[]
            def fake_fetch(start,end,session=None,api_key=None):
                calls.append((start,end))
                # One historical candle per chunk; current day not yet published
                last=min(end,date(2026,11,20))
                return [{"date":last.isoformat(),"close":20000.0}] if last>=start else []
            with patch("taiex_fugle_store_v1.fetch_range",side_effect=fake_fetch):
                first=update(as_of=day,path=path,max_chunks=2)
                second=update(as_of=day,path=path,max_chunks=2)
            self.assertEqual(len(calls),4)
            self.assertGreater(calls[2][0],calls[1][1])
            self.assertGreaterEqual(second["stored"],first["stored"])
            self.assertNotEqual(second["latest"],day.isoformat())
            self.assertTrue(read_store(path))

if __name__=="__main__":
    unittest.main()
