import tempfile
import unittest
from datetime import date
from pathlib import Path
from taiex_market_history_v1 import snapshot
from taiex_twse_store_v1 import parse_month, read_store, write_store, month_starts


class TAIEXTWSEStoreTest(unittest.TestCase):
    def test_twse_roc_index_column_by_name(self):
        payload = {"stat":"OK", "fields":["日期","發行量加權股價指數","交易股數"],"data":[["115/11/20","27,123.45","123"]]}
        self.assertEqual(parse_month(payload),[{"date":"2026-11-20","close":27123.45}])

    def test_twse_missing_index_rejected(self):
        with self.assertRaises(ValueError):
            parse_month({"stat":"OK","fields":["日期","交易股數"],"data":[["115/11/20","123"]]})

    def test_persistent_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"taiex.json"
            write_store(p,[{"date":"2026-11-20","close":100}])
            self.assertEqual(read_store(p),[{"date":"2026-11-20","close":100.0}])

    def test_month_sequence(self):
        self.assertEqual([x.isoformat() for x in month_starts(date(2025,12,1),date(2026,2,1))],["2025-12-01","2026-01-01","2026-02-01"])

    def test_completed_week_available_after_friday(self):
        rows=[{"date":"2026-11-20","close":100}]
        self.assertEqual(snapshot(rows,"2026-11-21")["completed_week_count"],1)
        self.assertEqual(snapshot(rows,"2026-11-20")["completed_week_count"],0)


if __name__ == "__main__":
    unittest.main()
