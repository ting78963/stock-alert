import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from research.premarket_market_brief_v1 import build_market_brief
from research.premarket_tx_fugle_v1 import parse_tx

NOW=datetime(2026,11,24,8,54,tzinfo=ZoneInfo("Asia/Taipei"))

class MarketBriefTests(unittest.TestCase):
    def test_assembly(self):
        seen={}
        def preview(**kwargs):
            seen.update(kwargs)
            return {"type":"flex"}
        card=build_market_brief(NOW,fx_fetch=lambda:{"value":"31"},sox_fetch=lambda _:{"value":"9000"},tx_fetch=lambda _:{"value":"35000"},cbc_read=lambda:[],preview=preview)
        self.assertEqual(set(seen["indicators"]),{"usdtwd","sox","tx"})
        self.assertEqual(seen["indicators"]["tx"]["value"],"35000")
        self.assertEqual(card["altText"],"2026-11-24 08:55 盤前簡報")
    def test_clock_advances_between_sources(self):
        times=iter([NOW+timedelta(seconds=n) for n in (15,30,45)])
        seen={}
        def preview(**kwargs):
            seen.update(kwargs)
            return {"type":"flex"}
        build_market_brief(NOW,fx_fetch=lambda:None,
            sox_fetch=lambda t:{"time":t},tx_fetch=lambda t:{"time":t},
            cbc_read=lambda:[],preview=preview,clock=lambda:next(times))
        self.assertEqual(seen["indicators"]["tx"]["time"],NOW+timedelta(seconds=30))
        self.assertEqual(seen["report_at"],NOW+timedelta(seconds=45))
    def test_source_failure(self):
        def fail(*args): raise OSError("offline")
        seen={}
        def preview(**kwargs):
            seen.update(kwargs)
            return {"type":"flex"}
        build_market_brief(NOW,fx_fetch=fail,sox_fetch=lambda _:{"value":"9000"},tx_fetch=fail,cbc_read=fail,preview=preview)
        self.assertIsNone(seen["indicators"]["tx"])
        self.assertIsNone(seen["indicators"]["usdtwd"])
        self.assertEqual(seen["indicators"]["sox"]["value"],"9000")
        self.assertEqual(seen["cbc_fx_rows"],[])
    def test_tx_day_quote(self):
        payload={"symbol":"TXFL6","date":"2026-11-24","lastTrade":{"price":35000,"time":"2026-11-24T08:54:05+08:00"}}
        prev={"symbol":"TXFL6","session":"day","date":"2026-11-23","close":34750}
        self.assertEqual(parse_tx(payload,NOW,prev)["change"],"+250 (+0.72%)")
        self.assertIsNone(parse_tx(payload,NOW,{**prev,"symbol":"TXFK6"})["change"])
        payload["lastTrade"]["time"]="2026-11-24T05:00:00+08:00"
        self.assertIsNone(parse_tx(payload,NOW,prev))
