import unittest
from datetime import date
from twse_session_gate_v1 import _ymd, is_scheduled_open

class TestROCDate(unittest.TestCase):
    def test_roc(self):
        self.assertEqual(_ymd('1151026'),date(2026,10,26))
        self.assertEqual(_ymd('20261027'),date(2026,10,27))
    def test_holiday(self):
        rows=[{'Date':'1151026','Name':'holiday'}]
        self.assertFalse(is_scheduled_open(date(2026,10,26),rows=rows))
        self.assertTrue(is_scheduled_open(date(2026,10,27),rows=rows))

if __name__=='__main__': unittest.main()
