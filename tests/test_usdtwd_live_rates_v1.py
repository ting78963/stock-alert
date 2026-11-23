import json
import unittest
from datetime import datetime,timezone
from io import BytesIO
from usdtwd_live_rates_v1 import parse_usdtwd,fetch_once,fetch_validated_once

def payload(rate="31.55",timestamp=1795416900):
    return [{"currency":"EUR/USD","rate":1.1,"timestamp":timestamp},
            {"currency":"USD/TWD","rate":rate,"bid":"31.54","ask":"31.56",
             "close":"31.50","timestamp":timestamp}]

class LiveRatesTests(unittest.TestCase):
    def test_parse_rate_and_timestamp(self):
        r=parse_usdtwd(payload())
        self.assertEqual(r["value"],31.55)
        self.assertEqual(r["source"],"live_rates")
        self.assertEqual(r["quote_kind"],"market_spot")
        self.assertEqual(r["bid"],31.54)
        self.assertEqual(r["ask"],31.56)
        self.assertEqual(r["quoted_at"],datetime.fromtimestamp(1795416900,timezone.utc).isoformat())
    def test_missing_symbol_rejected(self):
        with self.assertRaises(ValueError): parse_usdtwd([])
    def test_duplicate_symbol_rejected(self):
        with self.assertRaises(ValueError): parse_usdtwd(payload()+payload()[1:])
    def test_invalid_price_rejected(self):
        with self.assertRaises(ValueError): parse_usdtwd(payload(rate="nan"))
    def test_single_request(self):
        calls=[]
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return json.dumps(payload()).encode()
        def opener(req,timeout):
            calls.append((req.full_url,timeout))
            return Response()
        result=fetch_once(opener=opener)
        self.assertEqual(result["value"],31.55)
        self.assertEqual(len(calls),1)
    def test_fresh_validated_quote(self):
        ts=1795416900
        report_at=datetime.fromtimestamp(ts+30,timezone.utc)
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return json.dumps(payload(timestamp=ts)).encode()
        result=fetch_validated_once(report_at,opener=lambda req,timeout:Response())
        self.assertEqual(result["status"],"live")
        self.assertEqual(result["value"],31.55)
    def test_stale_validated_quote(self):
        ts=1795416900
        report_at=datetime.fromtimestamp(ts+600,timezone.utc)
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return json.dumps(payload(timestamp=ts)).encode()
        result=fetch_validated_once(report_at,opener=lambda req,timeout:Response())
        self.assertEqual(result["status"],"stale")
        self.assertIsNone(result["value"])
    def test_oversized_response_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return b"x"*2_000_001
        with self.assertRaises(ValueError):
            fetch_once(opener=lambda req,timeout:Response())

if __name__=="__main__":
    unittest.main()
