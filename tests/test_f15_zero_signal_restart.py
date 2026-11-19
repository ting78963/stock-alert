"""Regression tests for zero-signal F15 restart gate (offline; no LINE/API)."""
import json
import tempfile
import unittest
from datetime import datetime as RealDatetime
from pathlib import Path
from unittest.mock import patch

import f15_eod_signal_report as report
import f15_trajectory_store as trajectory


class FakeDatetime:
    now_value = RealDatetime(2026, 11, 19, 16, 31)
    @classmethod
    def now(cls, tz=None):
        return cls.now_value.replace(tzinfo=tz)


class ZeroSignalRestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.patches = [
            patch.object(report, "OUT", root / "f15_eod"),
            patch.object(report, "EVENTS", root / "events"),
            patch.object(report, "datetime", FakeDatetime),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.day = "2026-11-19"

    def test_zero_day_certified_after_close_and_restart_gate_passes(self):
        FakeDatetime.now_value = RealDatetime(2026, 11, 19, 16, 31)
        self.assertEqual(report.process_day(self.day), "zero_verified")
        self.assertTrue(trajectory.report_and_trajectory_complete(self.day))
        self.assertEqual(report.process_day(self.day), "already_sent")

    def test_no_certification_before_maintenance_window(self):
        FakeDatetime.now_value = RealDatetime(2026, 11, 19, 14, 0)
        self.assertEqual(report.process_day(self.day), "no_events")
        self.assertFalse(trajectory.report_and_trajectory_complete(self.day))

    def test_no_events_without_certificate_remains_blocked(self):
        self.assertFalse(trajectory.report_and_trajectory_complete(self.day))

    def test_new_event_after_zero_certificate_blocks_restart(self):
        FakeDatetime.now_value = RealDatetime(2026, 11, 19, 16, 31)
        self.assertEqual(report.process_day(self.day), "zero_verified")
        event_dir = report.EVENTS / self.day / "2330"
        event_dir.mkdir(parents=True)
        (event_dir / "signal_event.json").write_text(json.dumps({
            "date": self.day, "stock_id": "2330", "signal_class": "A",
            "recognition_time": "09:30:00", "line_sent": True
        }), encoding="utf-8")
        self.assertFalse(trajectory.report_and_trajectory_complete(self.day))


    def test_cleanup_and_restart_both_use_f15_gate(self):
        # Check the actual production orchestration, not only F15 helpers.
        import ast
        worker = (Path(__file__).resolve().parents[1] / "production_worker_v2_shared_ws.py").read_text(encoding="utf-8")
        tree = ast.parse(worker)
        for name in ("maybe_cleanup_after_maintenance", "maybe_restart_after_maintenance"):
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            src = ast.get_source_segment(worker, fn)
            self.assertIn("report_and_trajectory_complete(day)", src)
        self.assertIn("maybe_cleanup_after_maintenance(day,stage_done,notified_at)", worker)
        self.assertIn("maybe_restart_after_maintenance(day,stage_done,notified_at)", worker)

    def test_zero_day_rejected_if_certificate_missing_or_malformed(self):
        FakeDatetime.now_value = RealDatetime(2026, 11, 19, 16, 31)
        self.assertEqual(report.process_day(self.day), "zero_verified")
        registry_path = report.OUT / "sent_registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        del registry["dates"][self.day]["zero_signals_verified_at_taipei"]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        self.assertFalse(trajectory.report_and_trajectory_complete(self.day))

if __name__ == "__main__":
    unittest.main()
