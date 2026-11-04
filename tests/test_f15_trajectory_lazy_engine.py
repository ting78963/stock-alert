import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("trajectory", Path(__file__).resolve().parents[1] / "f15_trajectory_store.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TrajectoryLazyEngineTests(unittest.TestCase):
    def test_existing_records_do_not_load_engine(self):
        event = {"stock_id": "1301", "signal_class": "A", "recognition_time": "10:30"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = "2026-11-04"
            folder = root / day
            folder.mkdir()
            (folder / "1301_A_1030.json").write_text(json.dumps({
                "schema": mod.SCHEMA,
                "identity": {"date": day, "stock_id": "1301", "signal_class": "A", "recognition_time": "10:30"}
            }), encoding="utf-8")
            with patch.object(mod, "OUT", root), patch.object(mod.f15, "load_events", return_value=[event]), patch.object(mod.runpy, "run_path", side_effect=AssertionError("engine should not load")):
                result = mod.build_day(day)
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(json.loads((folder / "manifest.json").read_text())["count"], 1)

    def test_loop_skips_completed_prior_day_but_retries_failure(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        class StopLoop(Exception):
            pass

        days = ["2026-11-03", "2026-11-04"]
        attempts = []
        clock = datetime(2026, 11, 5, 16, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        ticks = [0]

        def fake_build(day):
            attempts.append(day)
            if day == days[1] and attempts.count(day) == 1:
                raise RuntimeError("temporary error")
            return {"day": day, "status": "ok", "written": 0, "skipped": 1}

        def fake_sleep(_):
            ticks[0] += 1
            if ticks[0] >= 3:
                raise StopLoop()

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mod, "OUT", Path(tmp)), patch.object(mod, "days", return_value=days), patch.object(mod, "datetime") as dt, patch.object(mod, "build_day", side_effect=fake_build), patch.object(mod.time, "sleep", side_effect=fake_sleep):
                dt.now.return_value = clock
                with self.assertRaises(StopLoop):
                    mod.loop()
        self.assertEqual(attempts, [days[0], days[1], days[1]])

    def test_today_is_rechecked_for_late_arriving_events(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        class StopLoop(Exception):
            pass

        today = "2026-11-05"
        attempts = []
        clock = datetime(2026, 11, 5, 16, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        ticks = [0]

        def fake_sleep(_):
            ticks[0] += 1
            if ticks[0] == 3:
                raise StopLoop()

        def fake_build(day):
            attempts.append(day)
            return {"day": day, "status": "ok", "written": 0, "skipped": 1}

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mod, "OUT", Path(tmp)), patch.object(mod, "days", return_value=[today]), patch.object(mod, "datetime") as dt, patch.object(mod, "build_day", side_effect=fake_build), patch.object(mod.time, "sleep", side_effect=fake_sleep):
                dt.now.return_value = clock
                with self.assertRaises(StopLoop):
                    mod.loop()
        self.assertEqual(attempts, [today, today, today])

if __name__ == "__main__":
    unittest.main()
