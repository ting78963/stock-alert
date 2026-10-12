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
