import sqlite3
import tempfile
import unittest
from pathlib import Path
from research.per_symbol_exception_policy_v1 import read_quarantined, should_scan, SystemicHistoryFailure

class SQLiteQuarantineTests(unittest.TestCase):
    def test_one_error_then_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/"test.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE fetch_error(symbol TEXT PRIMARY KEY, error TEXT, last_error_utc TEXT)")
                db.execute("INSERT INTO fetch_error VALUES (?,?,?)",("5355","HTTP 404","2026-10-30"))
            self.assertFalse(should_scan("5355",read_quarantined(dbpath)))
            self.assertTrue(should_scan("2330",read_quarantined(dbpath)))
            with sqlite3.connect(dbpath) as db:
                db.execute("DELETE FROM fetch_error WHERE symbol=?",("5355",))
            self.assertTrue(should_scan("5355",read_quarantined(dbpath)))
    def test_missing_table_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/"test.db"
            sqlite3.connect(dbpath).close()
            with self.assertRaises(SystemicHistoryFailure):
                read_quarantined(dbpath)

if __name__=="__main__":
    unittest.main()
