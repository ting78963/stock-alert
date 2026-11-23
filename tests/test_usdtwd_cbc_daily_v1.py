import unittest
from usdtwd_cbc_daily_v1 import parse_daily,trend_snapshot

class CBCFXTests(unittest.TestCase):
    def test_chinese_columns(self):
        self.assertEqual(parse_daily([{"日期":"2026/11/20","NTD/USD":"32.936"}]),[{"date":"2026-11-20","close":32.936}])
    def test_reject_unknown_columns(self):
        with self.assertRaises(ValueError):
            parse_daily([{"wrong":"x"}])
    def test_calculate_own_ma_and_currency_direction(self):
        rows=[{"date":f"2026-10-{i:02d}","close":30+i/100} for i in range(1,21)]
        snap=trend_snapshot(rows,"2026-10-22")
        self.assertIsNotNone(snap["daily_ma20"])
        self.assertEqual(snap["direction"],"TWD_depreciation")
        self.assertEqual(snap["quote_kind"],"official_daily_close")
    def test_no_same_day_close_in_morning(self):
        rows=[{"date":"2026-11-20","close":32.936},{"date":"2026-11-23","close":33.0}]
        snap=trend_snapshot(rows,"2026-11-23")
        self.assertEqual(snap["last_close"],32.936)

if __name__=="__main__":
    unittest.main()
