import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("f15_eod", Path(__file__).resolve().parents[1] / "f15_eod_signal_report.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class F15EodLoopTests(unittest.TestCase):
    def test_sent_days_skipped_and_failed_days_retried(self):
        class StopLoop(Exception):
            pass

        clock = datetime(2026, 11, 5, 16, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        prior, today = "2026-11-04", "2026-11-05"
        attempts = []
        ticks = [0]

        def fake_process(day, send_line):
            self.assertTrue(send_line)
            attempts.append(day)
            if day == today and attempts.count(day) == 1:
                raise RuntimeError("temporary failure")
            return "already_sent" if day == prior else "sent"

        def fake_sleep(_):
            ticks[0] += 1
            if ticks[0] >= 3:
                raise StopLoop()

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mod, "OUT", Path(tmp)), patch.object(mod, "days", return_value=[prior, today]), patch.object(mod, "datetime") as dt, patch.object(mod, "process_day", side_effect=fake_process), patch.object(mod.time, "sleep", side_effect=fake_sleep):
                dt.now.return_value = clock
                with self.assertRaises(StopLoop):
                    mod.loop()
        self.assertEqual(attempts, [prior, today, today])


if __name__ == "__main__":
    unittest.main()
