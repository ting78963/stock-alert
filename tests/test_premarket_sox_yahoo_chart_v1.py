import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
from research.premarket_sox_yahoo_chart_v1 import parse_sox_chart


def ts(day):
    return int(datetime.fromisoformat(day + "T16:00:00-05:00").timestamp())


class TestSoxYahooChart(unittest.TestCase):
    def test_previous_completed_daily_bar(self):
        data={"chart":{"result":[{"meta":{"symbol":"^SOX","regularMarketPrice":9999},
          "timestamp":[ts("2026-11-20"),ts("2026-11-23")],
          "indicators":{"quote":[{"close":[9500,9589.096]}]}}]}}
        with patch("research.premarket_sox_yahoo_chart_v1.datetime") as clock:
            clock.fromtimestamp.side_effect=datetime.fromtimestamp
            clock.now.return_value=datetime(2026,11,24,1,0,tzinfo=timezone.utc)
            result=parse_sox_chart(data)
        self.assertTrue(result["available"],result)
        self.assertEqual(result["close_date"],"2026-11-23")
        self.assertEqual(result["close"],9589.096)
        self.assertEqual(result["change_pct"],0.94)

    def test_wrong_symbol_fails_closed(self):
        self.assertFalse(parse_sox_chart({"chart":{"result":[{"meta":{"symbol":"NVDA"}}]}})["available"])

    def test_missing_daily_bars_fails_closed(self):
        self.assertFalse(parse_sox_chart({"chart":{"result":[{"meta":{"symbol":"^SOX"},"timestamp":[],"indicators":{"quote":[{"close":[]}]}}]}})["available"])

if __name__=="__main__":unittest.main()
