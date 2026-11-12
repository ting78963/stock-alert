# -*- coding: utf-8 -*-
import unittest
import os
import json
import urllib.error
from unittest.mock import patch
from a_vcp_line_notify_v1 import make_event, notify_once, send_line


class IndependentVcpLineTests(unittest.TestCase):
    def setUp(self):
        self.row = {"stock_id":"6150","name":"測試股票","close":78.4,
                    "change_rate":1.82,"total_volume":8824}
        self.decision = {"watch":{"pivot":77.5},"raw_vr5":2.66}
        self.event = make_event(self.row,self.decision,"2026-11-12","09:26:00")

    def test_no_fallback_to_existing_production_group(self):
        with patch.dict(os.environ, {"LINE_TOKEN":"test-token", "GROUP_ID":"production-group", "LINE_TO_ID":"production-to"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "A_VCP_LINE_TO_ID"):
                send_line({"type":"flex"}, "2026-11-12|6150")

    def test_pending_below_pivot_not_sent_or_marked(self):
        sent = {}
        calls = []
        event = dict(self.event, price=77.0)
        self.assertFalse(notify_once(event, sent, sender=lambda flex, key: calls.append(key)))
        self.assertEqual(sent, {})
        self.assertEqual(calls, [])

    def test_at_pivot_not_sent(self):
        sent = {}
        self.assertFalse(notify_once(dict(self.event, price=77.5), sent, sender=lambda flex, key: None))
        self.assertEqual(sent, {})

    def test_persisted_dedupe_survives_restart(self):
        sent = {}
        self.assertTrue(notify_once(self.event, sent, sender=lambda flex, key: None))
        reloaded = json.loads(json.dumps({"vcp_line_sent": sent}))["vcp_line_sent"]
        calls = []
        self.assertFalse(notify_once(self.event, reloaded, sender=lambda flex, key: calls.append(key)))
        self.assertEqual(calls, [])

    def test_line_retry_key_stable_and_409_accepted(self):
        from unittest.mock import Mock
        reqs = []
        def accepted(req, timeout):
            reqs.append(req)
            return Mock(__enter__=lambda self: Mock(status=200),
                        __exit__=lambda self, exc_type, exc, tb: False)
        with patch.dict(os.environ, {"LINE_TOKEN":"test-token", "A_VCP_LINE_TO_ID":"test-only"}, clear=True):
            with patch("a_vcp_line_notify_v1.urllib.request.urlopen", side_effect=accepted):
                send_line({"type":"flex"}, "2026-11-12|6150")
                send_line({"type":"flex"}, "2026-11-12|6150")
            self.assertEqual(reqs[0].get_header("X-line-retry-key"), reqs[1].get_header("X-line-retry-key"))
            err = urllib.error.HTTPError("https://api.line.me", 409, "Conflict", {}, None)
            with patch("a_vcp_line_notify_v1.urllib.request.urlopen", side_effect=err):
                send_line({"type":"flex"}, "2026-11-12|6150")

    def test_line_500_remains_retryable(self):
        err = urllib.error.HTTPError("https://api.line.me", 500, "Server Error", {}, None)
        with patch.dict(os.environ, {"LINE_TOKEN":"test-token", "A_VCP_LINE_TO_ID":"test-only"}, clear=True):
            with patch("a_vcp_line_notify_v1.urllib.request.urlopen", side_effect=err):
                with self.assertRaises(urllib.error.HTTPError):
                    send_line({"type":"flex"}, "2026-11-12|6150")

    def test_actual_pivot_and_snapshot(self):
        self.assertEqual(self.event["pivot"],77.5)
        self.assertEqual(self.event["price"],78.4)

    def test_success_only_once(self):
        calls=[]
        sent={}
        sender=lambda flex,key:calls.append(key)
        self.assertTrue(notify_once(self.event,sent,sender=sender))
        self.assertFalse(notify_once(self.event,sent,sender=sender))
        self.assertEqual(calls,["2026-11-12|6150"])

    def test_failure_retries(self):
        sent={}
        def fail(flex,key):
            raise RuntimeError("offline test failure")
        with self.assertRaises(RuntimeError):
            notify_once(self.event,sent,sender=fail)
        self.assertEqual(sent,{})
        self.assertTrue(notify_once(self.event,sent,sender=lambda flex,key:None))

    def test_no_pivot_no_send(self):
        sent={}
        event=dict(self.event,pivot=None)
        calls=[]
        with self.assertRaises(ValueError):
            notify_once(event,sent,sender=lambda flex,key:calls.append(key))
        self.assertEqual(calls,[])

    def test_separate_from_b_discovered(self):
        # notify_once receives only VCP's own state, never A->B discovered.
        discovered={"2026-11-12":{"6150":{"source":"SURGE"}}}
        sent={}
        self.assertTrue(notify_once(self.event,sent,sender=lambda flex,key:None))
        self.assertIn("6150",discovered["2026-11-12"])
        self.assertIn("2026-11-12|6150",sent)


if __name__=="__main__":
    unittest.main()
