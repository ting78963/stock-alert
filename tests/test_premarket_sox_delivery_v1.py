import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from research.premarket_sox_card_v1 import build_premarket_sox_flex
from research.premarket_sox_delivery_v1 import deliver_premarket_once

TPE=ZoneInfo("Asia/Taipei")

def clock(hour,minute):return datetime(2026,11,24,hour,minute,tzinfo=TPE)

class TestPremarketDelivery(unittest.TestCase):
    def test_card_shape(self):
        card=build_premarket_sox_flex(clock(8,55),lambda _:{"type":"text","text":"費半 SOX  9,589.10","size":"sm"})
        self.assertEqual(card["type"],"flex")
        self.assertIn("08:55",card["altText"])
    def test_once_only(self):
        with tempfile.TemporaryDirectory() as d:
            sent=[]; p=Path(d)/"premarket.json"
            builder=lambda now:{"type":"flex","altText":"2026-11-24 08:55 盤前簡報","contents":{}}
            send=lambda card: sent.append(card) or True
            self.assertEqual(deliver_premarket_once(clock(8,54),send,p,builder),"not_due")
            self.assertEqual(deliver_premarket_once(clock(8,55),send,p,builder),"sent")
            self.assertEqual(deliver_premarket_once(clock(8,56),send,p,builder),"already_sent")
            self.assertEqual(len(sent),1)
    def test_failed_send_not_marked(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"premarket.json"
            with self.assertRaises(RuntimeError):
                deliver_premarket_once(clock(8,55),lambda _:False,p,lambda _:{"type":"flex"})
            self.assertFalse(p.exists())

if __name__=="__main__":unittest.main()
