import os
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
            card={"type":"flex","altText":"2026-11-24 08:55 盤前簡報","contents":{"type":"bubble"}}
            self.assertTrue(send_premarket_flex(card,opener))
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0].get_method(),"POST")
        self.assertTrue(seen[0].get_header("X-line-retry-key"))
    def test_already_accepted_retry(self):
        headers=Message()
        headers["x-line-accepted-request-id"]="accepted"
        def opener(req,timeout):
            raise HTTPError(req.full_url,409,"Conflict",headers,None)
        card={"type":"flex","altText":"2026-11-24 08:55 盤前簡報"}
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
