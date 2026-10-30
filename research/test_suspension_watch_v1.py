#!/usr/bin/env python3
"""Offline regression checks for suspension watch. No network, no production writes."""
import ast
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "phase1_fugle_daily_builder_v1.py"
import importlib.util
spec = importlib.util.spec_from_file_location("daily_builder", SRC)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class WatchTests(unittest.TestCase):
    def test_database_schema_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "stage.sqlite3"
            with builder.dbopen(p) as db:
                db.execute("INSERT INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc) VALUES(?,?,?)",
                           ("2067", "operator-confirmed", datetime.now(timezone.utc).isoformat()))
                db.commit()
            with builder.dbopen(p) as db:
                self.assertEqual(db.execute("SELECT symbol FROM suspension_watch").fetchone()[0], "2067")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM suspension_meta").fetchone()[0], 0)

    def test_twse_status_fails_closed_for_unknown_schema(self):
        from unittest.mock import patch
        from io import BytesIO
        import json
        with patch.object(builder.urllib.request,"urlopen",return_value=BytesIO(json.dumps([{"unknown":"2067"}]).encode())):
            self.assertIsNone(builder.twse_suspension_status("2067",datetime(2026,10,12).date()))

    def test_twse_status_confirms_active_interval(self):
        from unittest.mock import patch
        from io import BytesIO
        import json
        sample=[{"Code":"2067","TradingHaltDate":"1151001","TradingResumptionDate":"1151020"}]
        with patch.object(builder.urllib.request,"urlopen",return_value=BytesIO(json.dumps(sample).encode())):
            self.assertEqual(builder.twse_suspension_status("2067",datetime(2026,10,12).date()),"twse-twtawu")
        with patch.object(builder.urllib.request,"urlopen",return_value=BytesIO(json.dumps(sample).encode())):
            self.assertIsNone(builder.twse_suspension_status("2067",datetime(2026,10,20).date()))

    def test_twse_actual_render_response_is_historical_not_active(self):
        from unittest.mock import patch
        from io import BytesIO
        import json
        # Actual TWTAWU response obtained from Render on 2026-10-12.
        sample=[{"Number":"1","Code":"1218","Name":"泰山",
                 "TradingHaltDate":"1150813","TradingHaltTime":"080000",
                 "TradingResumptionDate":"1150814","TradingResumptionTime":"080000"}]
        with patch.object(builder.urllib.request,"urlopen",return_value=BytesIO(json.dumps(sample).encode())):
            self.assertIsNone(builder.twse_suspension_status("1218",datetime(2026,10,12).date()))
        with patch.object(builder.urllib.request,"urlopen",return_value=BytesIO(json.dumps(sample).encode())):
            self.assertEqual(builder.twse_suspension_status("1218",datetime(2026,8,13).date()),"twse-twtawu")

    def test_twse_network_failure_stays_unknown(self):
        from unittest.mock import patch
        from urllib.error import URLError
        with patch.object(builder.urllib.request,"urlopen",side_effect=URLError("offline")):
            self.assertIsNone(builder.twse_suspension_status("2067",datetime(2026,10,12).date()))

    def test_twse_different_symbol_is_not_confirmed(self):
        from unittest.mock import patch
        from io import BytesIO
        import json
        sample=[{"Code":"9999","TradingHaltDate":"1151001","TradingResumptionDate":""}]
        with patch.object(builder.urllib.request,"urlopen",return_value=BytesIO(json.dumps(sample).encode())):
            self.assertIsNone(builder.twse_suspension_status("2067",datetime(2026,10,12).date()))

    def test_full_watch_lifecycle_with_fake_fugle(self):
        import sys
        import json
        import urllib.error
        from unittest.mock import patch
        from datetime import timedelta
        day=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date()-timedelta(days=1)
        asof=(day+timedelta(days=1)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            f10=pathlib.Path(tmp)/"f10.sqlite3"
            dbpath=pathlib.Path(tmp)/"stage.sqlite3"
            with sqlite3.connect(f10) as db:
                db.execute("CREATE TABLE member(symbol TEXT)")
                db.execute("INSERT INTO member VALUES('2067')")
            argv=["builder","--asof",asof,"--f10",str(f10),"--db",str(dbpath),
                  "--delay","1","--max-retries","0","--history-calendar-days","200"]
            def run(fake_fetch,official=None):
                with patch.object(sys,"argv",argv),patch.dict(builder.os.environ,{"FUGLE_API_KEY":"test"}),patch.object(builder,"fetch",side_effect=fake_fetch),patch.object(builder.time,"sleep"),patch.object(builder,"twse_suspension_status",return_value=official):
                    builder.main()
            def missing(*args):
                raise urllib.error.HTTPError("fake",404,"missing",None,None)
            run(missing,"twse-twtawu")
            with sqlite3.connect(dbpath) as db:
                self.assertEqual(db.execute("SELECT last_probe_day FROM suspension_watch WHERE symbol='2067'").fetchone()[0],day.isoformat())
            # Same day's scheduled probe must be skipped.
            run(lambda *args:self.fail("same-day API request was not skipped"))
            # Next day: a valid current-day candle is recorded, but remains quarantined for manual review.
            nextday=day+timedelta(days=1)
            argv[argv.index("--asof")+1]=(nextday+timedelta(days=1)).isoformat()
            def recovered(*args):
                return {"symbol":"2067","data":[{"date":nextday.isoformat(),"open":10,"high":11,"low":9,"close":10.5,"volume":5000}]}
            run(recovered)
            with sqlite3.connect(dbpath) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM suspension_watch").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT last_probe_result FROM suspension_watch WHERE symbol='2067'").fetchone()[0],"READY_FOR_REVIEW")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE symbol='2067'").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT covered_through FROM fetch_status WHERE symbol='2067'").fetchone()[0],nextday.isoformat())

    def test_maintenance_plan_legacy_db_without_watch_table(self):
        import importlib.util
        from datetime import timedelta
        spec=importlib.util.spec_from_file_location("daily_maintenance_legacy",ROOT/"a_daily_incremental_maintenance_v1.py")
        maintenance=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(maintenance)
        now=datetime.now(timezone(timedelta(hours=8))).replace(hour=16,minute=0,second=0,microsecond=0)
        today=now.date().isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            f10=pathlib.Path(tmp)/"f10.sqlite3"
            stage=pathlib.Path(tmp)/"stage.sqlite3"
            with sqlite3.connect(f10) as db:
                db.execute("CREATE TABLE member(symbol TEXT)")
                db.execute("INSERT INTO member VALUES('2067')")
            with sqlite3.connect(stage) as db:
                db.execute("CREATE TABLE fetch_status(symbol TEXT PRIMARY KEY,covered_through TEXT,last_success_utc TEXT)")
                db.execute("INSERT INTO fetch_status VALUES(?,?,?)",("2067","2026-10-01","2026-10-01"))
            self.assertEqual(maintenance.plan(now,stage,f10)["due"],1)
            with sqlite3.connect(stage) as db:
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='suspension_watch'").fetchone())

    def test_maintenance_plan_keeps_watched_stock_due(self):
        import importlib.util
        from datetime import timedelta
        spec=importlib.util.spec_from_file_location("daily_maintenance",ROOT/"a_daily_incremental_maintenance_v1.py")
        maintenance=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(maintenance)
        now=datetime.now(timezone(timedelta(hours=8))).replace(hour=16,minute=0,second=0,microsecond=0)
        today=now.date().isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            f10=pathlib.Path(tmp)/"f10.sqlite3"
            stage=pathlib.Path(tmp)/"stage.sqlite3"
            with sqlite3.connect(f10) as db:
                db.execute("CREATE TABLE member(symbol TEXT)")
                db.execute("INSERT INTO member VALUES('2067')")
            with builder.dbopen(stage) as db:
                db.execute("INSERT INTO fetch_status VALUES(?,?,?)",("2067",today,"2026-10-01"))
                db.execute("INSERT INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc,last_probe_day) VALUES(?,?,?,?)",
                           ("2067","operator-confirmed","2026-10-01",""))
            self.assertEqual(maintenance.plan(now,stage,f10)["due"],1)
            with sqlite3.connect(stage) as db:
                db.execute("UPDATE suspension_watch SET last_probe_day=? WHERE symbol='2067'",(today,))
            self.assertEqual(maintenance.plan(now,stage,f10)["due"],0)

    def test_watch_probe_day_is_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"stage.sqlite3"
            with builder.dbopen(p) as db:
                db.execute("INSERT INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc,last_probe_day,last_probe_result) VALUES(?,?,?,?,?)",
                           ("2067","operator-confirmed",datetime.now(timezone.utc).isoformat(),"2026-10-12","http404"))
                db.commit()
            with builder.dbopen(p) as db:
                row=db.execute("SELECT last_probe_day,last_probe_result FROM suspension_watch WHERE symbol='2067'").fetchone()
                self.assertEqual(row,("2026-10-12","http404"))

    def test_duplicate_watch_seed_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"stage.sqlite3"
            with builder.dbopen(p) as db:
                db.execute("INSERT INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc,last_probe_day) VALUES(?,?,?,?)",
                           ("2067","operator-confirmed","2026-10-01","2026-10-12"))
                db.execute("INSERT OR IGNORE INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc) VALUES(?,?,?)",
                           ("2067","operator-confirmed","2026-10-13"))
                self.assertEqual(db.execute("SELECT confirmed_at_utc,last_probe_day FROM suspension_watch").fetchone(),
                                 ("2026-10-01","2026-10-12"))

    def test_parse_rejects_wrong_identity(self):
        with self.assertRaisesRegex(ValueError, "symbol identity mismatch"):
            builder.parse("2067", {"symbol":"3625","data":[]}, "2026-10-01", "2026-10-12")

    def test_parse_rejects_invalid_ohlcv(self):
        with self.assertRaisesRegex(ValueError, "invalid OHLCV"):
            builder.parse("2067", {"symbol":"2067","data":[{
                "date":"2026-10-12","open":10,"high":9,"low":8,"close":10,"volume":1000
            }]}, "2026-10-01", "2026-10-12")

    def test_empty_reply_is_not_resumption(self):
        rows=builder.parse("2067",{"symbol":"2067","data":[]},"2026-10-01","2026-10-12")
        self.assertFalse(any(r[1]=="2026-10-12" and r[6]>0 for r in rows))

    def test_valid_current_day_candle_is_resumption(self):
        rows=builder.parse("2067",{"symbol":"2067","data":[{
            "date":"2026-10-12","open":10,"high":11,"low":9,"close":10.5,"volume":5000
        }]},"2026-10-01","2026-10-12")
        self.assertTrue(any(r[1]=="2026-10-12" and r[6]>0 for r in rows))

if __name__=="__main__":
    unittest.main()
