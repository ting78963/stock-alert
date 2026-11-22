import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from taiex_twse_store_v1 import update, read_store


class TAIEXUpdateTest(unittest.TestCase):
    def test_incremental_update_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "taiex.json"
            months = []
            def fake_fetch(month, session=None):
                months.append(month.strftime("%Y-%m"))
                return [{"date":month.isoformat(),"close":100.0}]
            with patch("taiex_twse_store_v1.fetch_month", side_effect=fake_fetch):
                first = update("2026-11-22", path=p)
                second = update("2026-11-22", path=p)
            self.assertGreaterEqual(first["stored"],36)
            self.assertEqual(second["stored"],first["stored"])
            self.assertEqual(months[-1],"2026-11")
            self.assertEqual(months[-2],"2026-11")
            self.assertEqual(len(read_store(p)),first["stored"])

    def test_failure_keeps_previous_months_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "taiex.json"
            attempts = []
            def sometimes_fail(month, session=None):
                attempts.append(month.strftime("%Y-%m"))
                if len(attempts)==3:
                    raise ConnectionError("simulated TWSE failure")
                return [{"date":month.isoformat(),"close":100.0}]
            with patch("taiex_twse_store_v1.fetch_month", side_effect=sometimes_fail):
                with self.assertRaises(ConnectionError):
                    update("2026-11-22", path=p)
            self.assertEqual(len(read_store(p)),2)
            with patch("taiex_twse_store_v1.fetch_month",return_value=[{"date":"2024-02-01","close":100.0}]) as fake:
                with self.assertRaises(ValueError):
                    update("2026-11-22", path=p)
                self.assertEqual(fake.call_count,1)


if __name__=="__main__":
    unittest.main()
