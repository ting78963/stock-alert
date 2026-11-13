import unittest
from datetime import date
from twse_session_gate_v1 import is_scheduled_open, SessionGateError

NEXT_YEAR = [{"Date": "1160101", "Name": "中華民國開國紀念日"}]

class TwseCalendarRolloverTests(unittest.TestCase):
    def test_2026_nov_13_open_despite_2027_api(self):
        self.assertTrue(is_scheduled_open(date(2026, 11, 13), rows=NEXT_YEAR))

    def test_2026_known_holidays_stay_closed(self):
        for day in ("2026-02-12", "2026-02-20", "2026-10-26", "2026-12-25"):
            with self.subTest(day=day):
                self.assertFalse(is_scheduled_open(date.fromisoformat(day), rows=NEXT_YEAR))

    def test_extraordinary_2026_closure_stays_closed(self):
        self.assertFalse(is_scheduled_open(date(2026, 10, 23), rows=NEXT_YEAR))

    def test_other_year_still_fails_closed(self):
        with self.assertRaises(SessionGateError):
            is_scheduled_open(date(2028, 11, 13), rows=NEXT_YEAR)

    def test_same_year_live_schedule_still_authoritative(self):
        self.assertFalse(is_scheduled_open(date(2026, 11, 13), rows=[{"Date":"1151113","Name":"臨時休市"}]))

if __name__ == "__main__":
    unittest.main()
