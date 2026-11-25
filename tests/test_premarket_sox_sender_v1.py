import os
import json
import uuid
from premarket_market_flex_v1 import build_premarket_flex

def fixture():
    card=build_premarket_flex({"tx":{"value":"40,500","change":"+176 (+0.44%)","previous_close":"40,324"}})
    card["altText"]="2026-11-24 08:55 盤前簡報"
    return card

from urllib.error import HTTPError
from email.message import Message
import unittest
from unittest.mock import patch
from research.premarket_sox_sender_v1 import send_premarket_flex

class FakeResponse:
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):pass

class TestPremarketSender(unittest.TestCase):
    def test_separate_retry_namespace(self):
        seen=[]
        def opener(req,timeout):seen.append(req);return FakeResponse()
        with patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test-token","LINE_TO_ID":"test-group"}):
            card=fixture()
            self.assertTrue(send_premarket_flex(card,opener))
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0].get_method(),"POST")
        self.assertEqual(seen[0].get_header("X-line-retry-key"),str(uuid.uuid5(uuid.NAMESPACE_URL,"premarket-brief-0855:2026-11-24")))
        messages=json.loads(seen[0].data)["messages"]
        self.assertEqual(len(messages),2)
        first,second=messages
        a=json.dumps(first,ensure_ascii=False)
        b=json.dumps(second,ensure_ascii=False)
        self.assertIn("大盤趨勢與持股策略",a)
        self.assertIn("全球市場與開盤研判",b)
        self.assertNotIn("40,500",a)
        self.assertIn("40,500",b)
        self.assertIn("前收 40,324",b)
        self.assertIn("01 / 02",a)
        self.assertIn("02 / 02",b)
        self.assertIn("今日市場多空研判",b)
        self.assertNotIn("今日市場多空研判",a)
    def test_already_accepted_retry(self):
        headers=Message()
        headers["x-line-accepted-request-id"]="accepted"
        def opener(req,timeout):
            raise HTTPError(req.full_url,409,"Conflict",headers,None)
        card=fixture()
        with patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test-token","LINE_TO_ID":"test-group"}):
            self.assertTrue(send_premarket_flex(card,opener))
            del headers["x-line-accepted-request-id"]
            with self.assertRaises(HTTPError):
                send_premarket_flex(card,opener)
    def test_bad_card_never_sent(self):
        with patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test-token","LINE_TO_ID":"test-group"}):
            with self.assertRaises(ValueError):
                send_premarket_flex({"type":"flex","altText":"2026-11-24 市場資料維護完成"},lambda *args:None)

if __name__=="__main__":unittest.main()
