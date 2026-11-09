"""Read-only indicator snapshot integration tests, no production signal or LINE."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from line_indicator_snapshot_v1 import compute_indicators

class SnapshotTests(unittest.TestCase):
    def test_completed_history_and_partial_today(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "history.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE daily_ohlcv (symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL)")
                from datetime import date, timedelta
                d = date(2026, 5, 4)
                items = []
                for i in range(110):
                    while d.weekday() > 4:
                        d += timedelta(days=1)
                    price = 80 + i * .2
                    items.append(("1301", d.isoformat(), price, price + 1, price - 1, price))
                    d += timedelta(days=1)
                db.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?)", items)
            today = "2026-10-26"
            minutes = [{"date": today, "minute": "09:00:00", "open": 102, "high": 104, "low": 101, "close": 103}]
            result = compute_indicators("1301", today, minutes, "09:00:59", dbpath)
            self.assertIsInstance(result.get("osc"), float)
            self.assertIn("weekly_kd", result)
            self.assertIn("ma_cross_day", result)
            self.assertIn("strong_buy", result)
            self.assertIn("ma20_first_above", result)
            self.assertIsInstance(result["ma20_first_above"], bool)
            self.assertEqual(compute_indicators("1301", today, minutes, "08:59:59", dbpath), {})
            self.assertEqual(compute_indicators("9999", today, minutes, "09:00:59", dbpath), {})

    def test_unmocked_history_to_line_card(self):
        from line_signal_notifier_v3 import build_flex
        from line_indicator_flex_preview_v1 import enrich_preview
        with tempfile.TemporaryDirectory() as temp:
            dbpath=Path(temp)/"history.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE daily_ohlcv (symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL)")
                from datetime import date, timedelta
                d=date(2026,1,5)
                rows=[]
                for i in range(160):
                    while d.weekday()>4:
                        d+=timedelta(days=1)
                    p=80+i*.12
                    rows.append(("1301",d.isoformat(),p,p+1,p-1,p))
                    d+=timedelta(days=1)
                db.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?)",rows)
            today="2026-10-26"
            minute_rows=[{"date":today,"minute":"09:00:00","open":100,"high":102,"low":99,"close":101}]
            indicators=compute_indicators("1301",today,minute_rows,"09:00:59",dbpath)
            self.assertIsInstance(indicators.get("osc"),float)
            event={"stock_id":"1301","stock_name":"台塑","signal_class":"B",
                   "recognition_time":"09:00:00","date":today}
            base=build_flex(event)
            card=enrich_preview(base,indicators)
            self.assertIn("OSC",str(card))
            self.assertIn("立即買進",str(card))
            self.assertEqual(len(card["contents"]["body"]["contents"]),len(base["contents"]["body"]["contents"])+1)

if __name__ == "__main__":
    unittest.main()
