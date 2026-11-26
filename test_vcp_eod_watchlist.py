import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from vcp_scan_once_adapter import VcpScanOnceRuntime
from vcp_eod_watchlist_v1 import classify,build_flex

class EodTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selector=VcpScanOnceRuntime(lambda:datetime(2026,11,26,17,tzinfo=ZoneInfo("Asia/Taipei"))).engine.selector
    def bars(self, tail=100, volume=600, previous=100):
        prices=[100]+[90,110]*10+[96,104]*10+[99.8,100.2]*9+[previous,tail]
        # The first prior-20 bar belongs to the preceding contraction segment.
        # Keep it below the intended breakout threshold, not at 104.
        prices[-21]=100.2
        return [((datetime(2026,11,26)-timedelta(days=len(prices)-1-i)).date().isoformat(),p,volume if i==len(prices)-1 else 600) for i,p in enumerate(prices)]
    def test_near(self):
        r=classify(self.selector,"2330",self.bars())
        self.assertEqual(r["category"],"near")
        self.assertAlmostEqual(r["threshold"],100.2*1.003)
    def test_first(self):
        r=classify(self.selector,"2330",self.bars(101,900))
        self.assertEqual(r["category"],"first_breakout")
    def test_second(self):
        self.assertIsNone(classify(self.selector,"2330",self.bars(102,900,101)))
    def test_prior_active_breakout_not_new(self):
        from unittest.mock import Mock
        selector=Mock()
        selector.track={}
        bars=self.bars(101,900)
        def analyze(closes,vols,symbol,dates):
            selector.track[symbol]={"pivot":100.2,"breakoutDate":dates[-1]}
            return {"pivot":100.2,"justBroke":True,"contracting":True,"breakDays":1}
        selector.analyze_vcp.side_effect=analyze
        self.assertIsNone(classify(selector,"2330",bars))

    def test_volume(self):
        r=classify(self.selector,"2330",self.bars(101,100))
        self.assertIsNone(r)
    def test_near_distance_gate(self):
        from unittest.mock import Mock
        selector=Mock()
        selector.track={}
        selector.analyze_vcp.return_value={"pivot":100,"status":"final_contraction","justBroke":False}
        for close,expected in ((97.49,False),(97.5,True),(99.9,True),(100,False),(75,False)):
            self.assertEqual(classify(selector,"2330",self.bars(close)) is not None,expected)
        selector.analyze_vcp.return_value["breakoutTrack"]={"pivot":110}
        self.assertIsNone(classify(selector,"2330",self.bars(99.9)))

    def test_vertical_push(self):
        import json, os
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from vcp_eod_watchlist_v1 import send_once
        row=classify(self.selector,"2330",self.bars())
        row["name"]="test"
        result=dict(day="2026-11-26",near=[row]*8,first_breakout=[],evaluated=8,missing_metadata=0,missing_history=0)
        with TemporaryDirectory() as d, patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test","LINE_TO_ID":"test"}), patch("urllib.request.urlopen") as push:
            push.return_value.__enter__.return_value.status=200
            self.assertTrue(send_once(result,Path(d)/"sent.json"))
            messages=json.loads(push.call_args.args[0].data)["messages"]
            self.assertEqual(len(messages),2)
            self.assertTrue(all(m["contents"]["type"]=="bubble" for m in messages))

    def test_liquidity_boundary(self):
        for prior,expected in ((532,False),(533.4,True)):
            bars=[(d,p,prior if i<60 else 100) for i,(d,p,v) in enumerate(self.bars())]
            self.assertEqual(classify(self.selector,"2330",bars) is not None,expected)
        for volume,expected in ((799,False),(800,True)):
            bars=[(d,p,500 if i<60 else volume) for i,(d,p,v) in enumerate(self.bars(101,volume))]
            self.assertEqual(classify(self.selector,"2330",bars) is not None,expected)

    def test_page_counts_and_batches(self):
        import json, os
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from vcp_eod_watchlist_v1 import send_once
        row=classify(self.selector,"2330",self.bars())
        row["name"]="test"
        for count,pages in ((20,4),(30,5),(50,9),(100,17)):
            result=dict(day="2026-11-26",near=[dict(row,symbol=str(1000+i)) for i in range(count)],first_breakout=[],evaluated=count,missing_metadata=0,missing_history=0)
            with TemporaryDirectory() as d, patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test","LINE_TO_ID":"test"}), patch("urllib.request.urlopen") as push:
                push.return_value.__enter__.return_value.status=200
                self.assertTrue(send_once(result,Path(d)/"sent.json"))
                batches=[json.loads(call.args[0].data)["messages"] for call in push.call_args_list]
                self.assertEqual(sum(map(len,batches)),pages)
                self.assertTrue(all(1<=len(b)<=5 for b in batches))
                raw=json.dumps(batches,ensure_ascii=False)
                for i in range(count):
                    self.assertEqual(raw.count(str(1000+i)+" test"),1)

    def test_short(self):
        self.assertIsNone(classify(self.selector,"2330",self.bars()[-30:]))
    def test_reference_and_white_flex(self):
        import json
        bars=self.bars()
        bars=[(d,p,29055.5 if i<len(bars)-1 else 100) for i,(d,p,v) in enumerate(bars)]
        row=classify(self.selector,"2330",bars)
        self.assertEqual((row["volume_10"],row["volume_12"],row["volume_full"]),(7845,23971,43583))
        self.assertAlmostEqual(row["reference_price"],100.2*1.005)
        row["name"]="測試股票"
        result=dict(day="2026-11-26",near=[row],first_breakout=[],evaluated=1,missing_metadata=0,missing_history=0)
        flex=build_flex(result)
        self.assertEqual(flex[0]["contents"]["body"]["backgroundColor"],"#FFFFFF")
        raw=json.dumps(flex,ensure_ascii=False)
        for s in ("7,845","23,971","43,583","10:00 前","12:00 前","bold"):
            self.assertIn(s,raw)
        result["near"]=[dict(row,symbol=str(1000+i)) for i in range(1500)]
        flex=build_flex(result)
        self.assertEqual(len(flex),250)
        self.assertTrue(all(m["contents"]["type"]=="bubble" for m in flex))
        self.assertTrue(all(len(json.dumps(m["contents"],ensure_ascii=False,separators=(",",":")).encode())<=29000 for m in flex))
        self.assertNotIn("未列出",json.dumps(flex,ensure_ascii=False))

    def test_flex(self):
        result=dict(day="2026-11-26",near=[],first_breakout=[],evaluated=1,missing_metadata=0,missing_history=0)
        self.assertEqual(build_flex(result)[0]["type"],"flex")
    def test_zero_matches_is_success(self):
        import json, os
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from vcp_eod_watchlist_v1 import send_once
        result=dict(day="2026-11-26",near=[],first_breakout=[],evaluated=1447,missing_metadata=0,missing_history=0)
        flex=build_flex(result)
        self.assertEqual(json.dumps(flex,ensure_ascii=False).count("無符合股票"),2)
        with TemporaryDirectory() as d, patch.dict(os.environ,{"LINE_CHANNEL_ACCESS_TOKEN":"test","LINE_TO_ID":"test"}), patch("urllib.request.urlopen") as push:
            push.return_value.__enter__.return_value.status=200
            marker=Path(d)/"sent.json"
            self.assertTrue(send_once(result,marker))
            self.assertTrue(marker.exists())
            self.assertFalse(send_once(result,marker))
            push.assert_called_once()

    def test_database_market_scale(self):
        import json, sqlite3, time, tracemalloc, resource
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from vcp_eod_watchlist_v1 import scan_database
        with TemporaryDirectory() as d:
            root=Path(d)
            daily=root/"daily.sqlite3"
            f10=root/"f10.sqlite3"
            metadata=root/"metadata.json"
            symbols=[str(1000+i) for i in range(1500)]
            bars=self.bars()
            with sqlite3.connect(daily) as db:
                db.execute("CREATE TABLE daily_ohlcv(symbol TEXT,day TEXT,close REAL,volume_zhang REAL,PRIMARY KEY(symbol,day))")
                db.execute("CREATE TABLE fetch_status(symbol TEXT PRIMARY KEY,covered_through TEXT)")
                db.executemany("INSERT INTO daily_ohlcv VALUES(?,?,?,?)",((s,*b) for s in symbols for b in bars))
                db.executemany("INSERT INTO fetch_status VALUES(?,?)",((s,"2026-11-26") for s in symbols))
            with sqlite3.connect(f10) as db:
                db.execute("CREATE TABLE member(symbol TEXT PRIMARY KEY)")
                db.executemany("INSERT INTO member VALUES(?)",((s,) for s in symbols))
            metadata.write_text(json.dumps({"symbols":{s:{"symbol":s,"name":s} for s in symbols}}))
            tracemalloc.start()
            started=time.monotonic()
            try:
                with patch.object(self.selector,"basic_code_ok",return_value=True), patch.object(self.selector,"meta_ok",return_value=True):
                    result=scan_database("2026-11-26",daily,f10,metadata,self.selector)
                _,peak=tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            elapsed=time.monotonic()-started
            print(f"EOD SQLite 1500: {elapsed:.2f}s, Python peak {peak/1048576:.2f} MiB, test process peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.2f} MiB")
            self.assertEqual(result["evaluated"],1500)
            self.assertEqual(len(result["near"]),1500)
            self.assertLess(peak,30*1048576)
            self.assertLess(elapsed,120)

    def test_market_scale(self):
        import time,tracemalloc
        bars=self.bars()
        tracemalloc.start()
        started=time.monotonic()
        try:
            for i in range(1500):
                row=classify(self.selector,str(1000+i),bars)
                self.assertEqual(row["category"],"near")
            current,peak=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        print(f"EOD 1500 symbols: {time.monotonic()-started:.2f}s, Python allocation peak {peak/1048576:.2f} MiB")
        self.assertLess(peak,10*1048576)

    def test_duplicate_marker(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from vcp_eod_watchlist_v1 import send_once
        with TemporaryDirectory() as d:
            marker=Path(d)/"sent.json"
            marker.write_text('{"sent":true}')
            with patch("urllib.request.urlopen") as push:
                self.assertFalse(send_once({"day":"2026-11-26"},marker))
                push.assert_not_called()

if __name__=="__main__":
    unittest.main()
