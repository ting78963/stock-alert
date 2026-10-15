# -*- coding: utf-8 -*-
"""Offline unit tests for isolated EOD coordinator. No API/LINE/production writes."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eod_coordinator import EODCoordinator, Phase

DAY = "2026-10-15"
KEY = DAY + "|2330"
OK = dict(queue_drained=True, worker_exited=True, final_rest_verified=True,
          final_evaluation_ok=True, notification_settled=True, persistence_ok=True)

class EODCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.c = EODCoordinator(DAY)

    def test_successful_close(self):
        self.assertTrue(self.c.claim(KEY))
        self.assertTrue(self.c.publish(KEY, object()))
        self.c.begin_close()
        self.assertFalse(self.c.claim(DAY + "|2317"))
        self.assertTrue(self.c.complete(KEY, **OK))
        self.assertTrue(self.c.finalize())
        self.assertEqual(self.c.snapshot().phase, Phase.CLOSED)

    def test_inflight_launch_cannot_publish_after_close(self):
        self.assertTrue(self.c.claim(KEY))
        self.assertEqual(self.c.begin_close().pending_launches, 1)
        self.assertFalse(self.c.publish(KEY, object()))
        self.assertTrue(self.c.finalize())

    def test_all_six_checks_fail_closed_individually(self):
        for name in OK:
            c = EODCoordinator(DAY)
            c.claim(KEY)
            c.publish(KEY, object())
            c.begin_close()
            checks = dict(OK)
            checks[name] = False
            self.assertFalse(c.complete(KEY, **checks), name)
            self.assertEqual(c.snapshot().held, 1)
            self.assertFalse(c.finalize())
            self.assertTrue(c.complete(KEY, **OK))
            self.assertTrue(c.finalize())

    def test_wrong_day_rejected(self):
        with self.assertRaises(ValueError):
            self.c.claim("2026-10-16|2330")

    def test_cannot_complete_without_closing(self):
        self.c.claim(KEY)
        self.c.publish(KEY, object())
        with self.assertRaises(RuntimeError):
            self.c.complete(KEY, **OK)

    def test_49_completed_four_prior_line_excluded(self):
        keys = [DAY + "|" + str(1000 + i) for i in range(49)]
        for k in keys:
            self.assertTrue(self.c.claim(k))
            self.assertTrue(self.c.publish(k, object()))
        self.c.begin_close()
        for k in keys:
            self.assertTrue(self.c.complete(k, **OK))
        self.assertTrue(self.c.finalize())
        self.assertEqual(self.c.snapshot().completed, 49)

if __name__ == "__main__":
    print("RESEARCH ONLY | NO API | NO LINE | NO PRODUCTION WRITE")
    unittest.main(verbosity=2)
