"""Offline regressions for UNKNOWN audit dedup and daily retention."""
import json
import tempfile
import unittest
from pathlib import Path
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

    def test_cleanup_does_not_run_in_market_hours(self):
        scanner.append_event({"type": "vcp_unknown", "date": "2026-11-07", "symbol": "1301", "reason": "MISSING"})
        before = (self.root / "events.jsonl").read_bytes()
        with patch.object(scanner, "is_market_window", return_value=True):
            self.assertEqual(scanner.maintain_unknown_event_log("2026-11-10"), {"skipped_market": 1})
        self.assertEqual((self.root / "events.jsonl").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
