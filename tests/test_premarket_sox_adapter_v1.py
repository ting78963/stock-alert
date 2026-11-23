import unittest
from research.premarket_sox_adapter_v1 import sox_close_snapshot


class SoxAdapterTests(unittest.TestCase):
    def test_uses_existing_strong_stock_quote_fields(self):
        result = sox_close_snapshot({"close": 7000, "prev": 6900, "chg_pct": 99}, "2026-11-23", "2026-11-24")
        self.assertTrue(result["available"])
        self.assertEqual(result["change_pct"], 1.45)
        self.assertEqual(result["close_date"], "2026-11-23")

    def test_no_undated_quote(self):
        self.assertFalse(sox_close_snapshot({"close": 7000, "prev": 6900}, None, "2026-11-24")["available"])

    def test_rejects_future_date(self):
        self.assertFalse(sox_close_snapshot({"close": 7000, "prev": 6900}, "2026-11-25", "2026-11-24")["available"])

    def test_rejects_invalid_previous_close(self):
        self.assertFalse(sox_close_snapshot({"close": 7000, "prev": 0}, "2026-11-23", "2026-11-24")["available"])


if __name__ == "__main__":
    unittest.main()
