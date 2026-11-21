import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fugle_a_scanner_v2_4 as a
import production_worker_v2_shared_ws as b


class VcpIndependentHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = patch.object(b, "STATE_ROOT", Path(self.tmp.name))
        self.state.start()
        self.addCleanup(self.state.stop)
        self.day = "2026-11-10"
        self.payload = {
            "stock_id": "3141", "date": self.day, "discovered_at": "10:20:00",
            "source": "VCP", "name": "TEST", "vol_ratio": 2.0, "change_pct": 3.0,
            "vcp": {"pivot": 100.0, "price": 101.0, "volume_zhang": 1200, "recognition_time": "10:20:00"},
        }

    def test_surge_first_then_vcp_and_dedupe(self):
        b.f14_bootstrap(self.day)
        with patch.object(b, "runner_module") as runner, patch.object(b, "subscribe_symbol"), patch.object(b, "worker_loop"), patch.object(b, "b_time_expired", return_value=False), patch.object(b, "LINE_SEND", True), patch("a_vcp_line_notify_v1.notify_once") as send:
            class FakeRunner:
                def __init__(self, *args, **kwargs):
                    import threading
                    self.lock = threading.RLock()
                    self.retired = False
                def rest_reconcile(self, *args): pass
            runner.return_value = {"Runner": FakeRunner}
            surge = dict(self.payload, source="SURGE")
            surge.pop("vcp")
            self.assertTrue(b.launch_b(surge)["launched"])
            def record(event, sent):
                sent[event["date"] + "|" + event["stock_id"]] = True
                return True
            send.side_effect = record
            self.assertTrue(b.launch_b(self.payload)["vcp_flex_sent"])
            self.assertTrue(b.launch_b(self.payload)["duplicate"])
            self.assertEqual(send.call_count, 1)
            self.assertEqual(len(b._runners), 1)
            b._runners.clear(); b._queues.clear(); b._launching.clear()

    def test_vcp_first_then_surge(self):
        b.f14_bootstrap(self.day)
        with patch.object(b, "LINE_SEND", True), patch("a_vcp_line_notify_v1.notify_once") as send, patch.object(b, "runner_module") as runner, patch.object(b, "subscribe_symbol"), patch.object(b, "worker_loop"), patch.object(b, "b_time_expired", return_value=False):
            send.side_effect = lambda event, sent: (sent.update({event["date"] + "|" + event["stock_id"]: True}) or True)
            self.assertTrue(b.launch_b(self.payload)["vcp_flex_sent"])
            class FakeRunner:
                def __init__(self, *args, **kwargs):
                    import threading
                    self.lock = threading.RLock()
                    self.retired = False
                def rest_reconcile(self, *args): pass
            runner.return_value = {"Runner": FakeRunner}
            surge = dict(self.payload, source="SURGE")
            surge.pop("vcp")
            self.assertTrue(b.launch_b(surge)["launched"])
            b._runners.clear(); b._queues.clear(); b._launching.clear()

    def test_below_pivot_rejected_without_line(self):
        payload = dict(self.payload, vcp=dict(self.payload["vcp"], price=99.0))
        with patch.object(b, "LINE_SEND", True), patch("a_vcp_line_notify_v1.notify_once") as send:
            with self.assertRaises(ValueError):
                b.launch_b(payload)
            send.assert_not_called()

    def test_failure_retry_and_restart_dedupe(self):
        with patch.object(b, "LINE_SEND", True), patch("a_vcp_line_notify_v1.notify_once") as send:
            def send_once(event, sent):
                if send.call_count == 1:
                    raise RuntimeError("network")
                sent[event["date"] + "|" + event["stock_id"]] = True
                return True
            send.side_effect = send_once
            with self.assertRaises(RuntimeError):
                b.launch_b(self.payload)
            self.assertTrue(b.launch_b(self.payload)["vcp_flex_sent"])
            self.assertTrue(b.launch_b(self.payload)["duplicate"])
            self.assertEqual(send.call_count, 2)

    def test_a_vcp_first_does_not_consume_surge(self):
        scanner = a.Scanner.__new__(a.Scanner)
        scanner.state = {"discovered": {}}
        scanner.layered_a_enabled = True
        scanner.bridge_url = "mock://b"
        sources = []
        def bridge(payload):
            sources.append(payload["source"])
            return {"http_status": 200, "body": {"ok": True, "key": payload["date"] + "|" + payload["stock_id"], "launched": True}}
        scanner.bridge_send = bridge
        vcp = {"code": "3141", "source": "VCP", "name": "TEST", "volRatio": 2.0, "chgPct": 3.0, "vcp": self.payload["vcp"]}
        surge = dict(vcp, source="SURGE")
        with patch.object(a, "save_json_atomic"), patch.object(a, "append_event"):
            self.assertTrue(scanner.handoff_hit(vcp, self.day))
            self.assertTrue(scanner.handoff_hit(surge, self.day))
            self.assertFalse(scanner.handoff_hit(vcp, self.day))
            self.assertFalse(scanner.handoff_hit(surge, self.day))
        self.assertEqual(sources, ["VCP", "SURGE"])

    def test_a_handoff_dedupe_independent_of_surge(self):
        scanner = a.Scanner.__new__(a.Scanner)
        scanner.state = {"discovered": {}}
        scanner.layered_a_enabled = True
        scanner.bridge_url = "mock://b"
        scanner.bridge_send = lambda p: {"http_status": 200, "body": {"ok": True, "key": p["date"] + "|" + p["stock_id"], "launched": True}}
        hit = {"code": "3141", "source": "SURGE", "name": "TEST", "volRatio": 2.0, "chgPct": 3.0}
        vcp = dict(hit, source="VCP", vcp=self.payload["vcp"])
        with patch.object(a, "save_json_atomic"), patch.object(a, "append_event"):
            self.assertTrue(scanner.handoff_hit(hit, self.day))
            self.assertTrue(scanner.handoff_hit(vcp, self.day))
            self.assertFalse(scanner.handoff_hit(vcp, self.day))


if __name__ == "__main__":
    unittest.main()
