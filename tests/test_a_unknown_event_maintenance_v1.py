"""Offline regressions for UNKNOWN audit dedup and daily retention."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from collections import namedtuple
from unittest.mock import patch

import fugle_a_scanner_v2_4 as scanner


class UnknownEventMaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = scanner.OUTDIR
        scanner.OUTDIR = self.root
        self.addCleanup(setattr, scanner, "OUTDIR", self.original)
        scanner._UNKNOWN_EVENT_DAY = None
        scanner._UNKNOWN_EVENT_SEEN = set()

    def events(self):
        path = self.root / "events.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_duplicate_unknown_does_not_suppress_important_event(self):
        unknown = {"type": "vcp_unknown", "date": "2026-11-10", "symbol": "1301", "reason": "CACHE_MISS"}
        scanner.append_event(unknown)
        scanner.append_event(unknown)
        scanner.append_event({"type": "handoff", "date": "2026-11-10", "symbol": "1301"})
        scanner.append_event({"type": "handoff", "date": "2026-11-10", "symbol": "1301"})
        self.assertEqual([x["type"] for x in self.events()], ["vcp_unknown", "handoff", "handoff"])

    def test_restart_recovers_today_dedup_from_log(self):
        unknown = {"type": "surge_unknown", "date": "2026-11-10", "symbol": "1301", "reason": "MISSING"}
        scanner.append_event(unknown)
        scanner._UNKNOWN_EVENT_DAY = None
        scanner._UNKNOWN_EVENT_SEEN = set()
        scanner.append_event(unknown)
        self.assertEqual(len(self.events()), 1)

    def test_next_day_is_a_new_unknown(self):
        for day in ("2026-11-10", "2026-11-11"):
            scanner.append_event({"type": "vcp_unknown", "date": day, "symbol": "1301", "reason": "MISSING"})
        self.assertEqual(len(self.events()), 2)

    def test_daily_cleanup_keeps_recent_unknown_and_all_other_events(self):
        records = [
            {"type": "vcp_unknown", "date": "2026-11-07", "symbol": "1301", "reason": "MISSING"},
            {"type": "vcp_unknown", "date": "2026-11-10", "symbol": "1301", "reason": "MISSING"},
            {"type": "vcp_unknown", "date": "2026-11-10", "symbol": "1301", "reason": "MISSING"},
            {"type": "handoff", "date": "2026-11-07", "symbol": "1301"},
        ]
        (self.root / "events.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in records), encoding="utf-8"
        )
        with patch.object(scanner, "is_market_window", return_value=False):
            result = scanner.maintain_unknown_event_log("2026-11-10")
        self.assertEqual(result["removed"], 2)
        self.assertEqual([x["type"] for x in self.events()], ["vcp_unknown", "handoff"])

    def test_low_disk_aborts_without_touching_original(self):
        record = {"type": "vcp_unknown", "date": "2026-11-07", "symbol": "1301", "reason": "MISSING"}
        path = self.root / "events.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        original = path.read_bytes()
        with patch.object(scanner, "is_market_window", return_value=False):
            with patch("shutil.disk_usage", return_value=namedtuple('DiskUsage', 'total used free')(100000000, 99999999, 1)):
                with self.assertRaises(OSError):
                    scanner.maintain_unknown_event_log("2026-11-10")
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.root / "events.jsonl.unknown-maint.tmp").exists())

    def test_cross_process_lock_serializes_append_with_cleanup(self):
        """A separate Python interpreter cannot append while maintenance holds the lock."""
        script = (
            "import sys; from pathlib import Path; import fugle_a_scanner_v2_4 as scanner; "
            "scanner.OUTDIR=Path(sys.argv[1]); "
            "scanner.append_event({'type':'handoff','date':'2026-11-10','symbol':'1301'})"
        )
        process = None
        try:
            with scanner._unknown_event_guard():
                process = subprocess.Popen(
                    [sys.executable, "-c", script, str(self.root)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.communicate(timeout=0.4)
            _, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
            self.assertEqual([x["type"] for x in self.events()], ["handoff"])
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_cleanup_does_not_run_in_market_hours(self):
        scanner.append_event({"type": "vcp_unknown", "date": "2026-11-07", "symbol": "1301", "reason": "MISSING"})
        before = (self.root / "events.jsonl").read_bytes()
        with patch.object(scanner, "is_market_window", return_value=True):
            self.assertEqual(scanner.maintain_unknown_event_log("2026-11-10"), {"skipped_market": 1})
        self.assertEqual((self.root / "events.jsonl").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
