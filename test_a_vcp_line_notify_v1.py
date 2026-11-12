# -*- coding: utf-8 -*-
import unittest
import os
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
