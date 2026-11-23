import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from market_maintenance_delivery_v1 import deliver_once

TPE=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,23,17,10,tzinfo=TPE)
CARD={"type":"flex","altText":"test","contents":{"type":"bubble"}}

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/"sent.json"

    def test_send_once(self):
        sent=[]
        send=lambda card:sent.append(card)
        args=dict(state_path=self.state,report_builder=lambda now:CARD)
        self.assertEqual(deliver_once(NOW,send,**args),"sent")
        self.assertEqual(deliver_once(NOW,send,**args),"already_sent")
        self.assertEqual(len(sent),1)

    def test_failed_send_not_marked(self):
        def fail(card):
            raise RuntimeError("LINE failed")
        with self.assertRaises(RuntimeError):
            deliver_once(NOW,fail,state_path=self.state,report_builder=lambda now:CARD)
        self.assertFalse(self.state.exists())
        self.assertEqual(deliver_once(NOW,lambda card:None,state_path=self.state,report_builder=lambda now:CARD),"sent")

    def test_false_response_not_marked(self):
        with self.assertRaises(RuntimeError):
            deliver_once(NOW,lambda card:False,state_path=self.state,report_builder=lambda now:CARD)
        self.assertFalse(self.state.exists())

    def test_incomplete_report_waits_without_marking_sent(self):
        card={"type":"flex","altText":"2026-11-23 市場資料維護未完成","contents":{"type":"bubble"}}
        sent=[]
        result=deliver_once(NOW,lambda payload:sent.append(payload),state_path=self.state,report_builder=lambda now:card)
        self.assertEqual(result,"waiting_for_data")
        self.assertFalse(sent)
        self.assertFalse(self.state.exists())

    def test_outside_window(self):
        self.assertEqual(deliver_once(NOW.replace(hour=16),lambda card:None,state_path=self.state),"not_due")
        self.assertFalse(self.state.exists())

if __name__=="__main__":
    unittest.main()
