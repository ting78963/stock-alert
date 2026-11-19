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


if __name__ == "__main__":
    unittest.main()
