import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('ledger', Path(__file__).resolve().parents[1] / 'tools' / 'restart_attempt_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)
TPE = ZoneInfo('Asia/Taipei')

class LedgerTests(unittest.TestCase):
    def test_once_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = dt.datetime(2026, 11, 5, 19, tzinfo=TPE)
            self.assertTrue(ledger.reserve(tmp, now))
            self.assertFalse(ledger.reserve(tmp, now))
            self.assertTrue(ledger.reserve(tmp, now + dt.timedelta(days=1)))
    def test_naive_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ledger.reserve(tmp, dt.datetime(2026, 11, 5, 19))

if __name__ == '__main__':
    unittest.main()
