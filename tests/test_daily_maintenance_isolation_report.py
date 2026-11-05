import ast
import sqlite3
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "production_worker_v2_shared_ws.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "daily_maintenance_snapshot")
module = ast.Module(body=[fn], type_ignores=[])
namespace = {}
exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
snapshot = namespace["daily_maintenance_snapshot"]

class TestMaintenanceIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "history.db")
        self.f10 = str(Path(self.tmp.name) / "f10.db")
        with sqlite3.connect(self.f10) as c:
            c.execute("CREATE TABLE member(symbol TEXT)")
            c.executemany("INSERT INTO member VALUES(?)", [(str(i),) for i in range(1000,1020)])
        with sqlite3.connect(self.db) as c:
            c.executescript("CREATE TABLE fetch_status(symbol TEXT,covered_through TEXT); CREATE TABLE fetch_error(symbol TEXT,error TEXT); CREATE TABLE suspension_watch(symbol TEXT,last_probe_result TEXT,last_probe_day TEXT);")
            c.executemany("INSERT INTO fetch_status VALUES(?,?)", [(str(i),"2026-11-05") for i in range(1000,1018)])
            c.execute("INSERT INTO fetch_error VALUES('1018','HTTPError 404')")
            c.execute("INSERT INTO suspension_watch VALUES('1019','http404','2026-11-05')")

    def check(self):
        return snapshot("2026-11-05", self.db, self.f10)

    def test_small_isolation_allows_partial_report(self):
        s=self.check()
        self.assertTrue(s["safe"])
        self.assertEqual(s["pending"],0)
        self.assertEqual(len(s["errors"]),1)

    def test_unaccounted_stock_blocks_report(self):
        with sqlite3.connect(self.db) as c:
            c.execute("DELETE FROM fetch_error")
        self.assertFalse(self.check()["safe"])

    def test_stale_watch_blocks_report(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE suspension_watch SET last_probe_day='2026-11-04'")
        self.assertFalse(self.check()["safe"])

    def test_many_errors_block_report(self):
        with sqlite3.connect(self.db) as c:
            c.execute("DELETE FROM fetch_status WHERE CAST(symbol AS INT)>=1007")
            c.executemany("INSERT INTO fetch_error VALUES(?,?)", [(str(i),"bad") for i in range(1007,1018)])
        self.assertFalse(self.check()["safe"])

    def test_previous_day_coverage_blocks_report(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE fetch_status SET covered_through='2026-11-04' WHERE symbol='1000'")
        self.assertFalse(self.check()["safe"])

if __name__ == "__main__":
    unittest.main()
