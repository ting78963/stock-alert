import datetime as dt
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("worker_status", Path(__file__).resolve().parents[1] / "tools" / "worker_restart_status.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NOW = dt.datetime(2026, 11, 5, 19, 0, tzinfo=ZoneInfo("Asia/Taipei"))

class StatusTests(unittest.TestCase):
    def test_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = mod.snapshot(Path(tmp), NOW)
            self.assertFalse(result["line_sent"])
            self.assertFalse(result["database_ok"])
            self.assertIsNone(result["f15_complete"])
            self.assertIsNone(result["active_trading_jobs"])
            self.assertFalse(result["restart_attempted"])

    def test_valid_record_and_db_do_not_imply_restart_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "daily_maintenance_state"
            folder.mkdir()
            (folder / "2026-11-05.json").write_text(json.dumps({
                "schema": "daily_maintenance_state_v2",
                "date": "2026-11-05",
                "stages": ["DAILY_K", "F10"],
                "line_sent": True,
                "line_accepted_at": "2026-11-05T16:30:00+08:00"
            }), encoding="utf-8")
            with sqlite3.connect(root / "shared_history_stage_v1.sqlite3") as conn:
                conn.execute("CREATE TABLE proof (id INTEGER)")
            result = mod.snapshot(root, NOW)
            self.assertTrue(result["database_ok"])
            self.assertTrue(result["line_sent"])
            self.assertIsNone(result["f15_complete"])
            self.assertIsNone(result["active_trading_jobs"])
            self.assertIsNone(result["restart_attempted"])

    def test_f15_requires_matching_report_and_trajectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "f15_eod"
            (out / "trajectory_v1" / "2026-11-05").mkdir(parents=True)
            (out / "sent_registry.json").write_text(json.dumps({
                "schema": "f15_sent_v1", "dates": {"2026-11-05": {"total": 2}}
            }), encoding="utf-8")
            manifest = out / "trajectory_v1" / "2026-11-05" / "manifest.json"
            manifest.write_text(json.dumps({
                "schema": "f15_trajectory_v1", "date": "2026-11-05", "count": 1
            }), encoding="utf-8")
            with patch.dict("os.environ", {"PRODUCTION_STATE_DIR": str(root)}):
                self.assertIsNone(mod.snapshot(root, NOW)["f15_complete"])
                manifest.write_text(json.dumps({
                    "schema": "f15_trajectory_v1", "date": "2026-11-05", "count": 2
                }), encoding="utf-8")
                self.assertTrue(mod.snapshot(root, NOW)["f15_complete"])

    def test_reserved_attempt_blocks_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "restart_attempts"
            ledger.mkdir()
            (ledger / "2026-11-05.json").write_text("{}", encoding="utf-8")
            self.assertTrue(mod.snapshot(root, NOW)["restart_attempted"])

    def test_legacy_record_cannot_invent_acceptance_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "daily_maintenance_state"
            folder.mkdir()
            (folder / "2026-11-05.json").write_text(json.dumps({
                "schema": "daily_maintenance_state_v1",
                "date": "2026-11-05",
                "stages": ["DAILY_K", "F10"], "line_sent": True
            }), encoding="utf-8")
            result = mod.snapshot(root, NOW)
            self.assertFalse(result["line_sent"])
            self.assertIsNone(result["line_accepted_at"])

if __name__ == "__main__":
    unittest.main()
