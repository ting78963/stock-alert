import unittest
from research.premarket_sox_flex_section_v1 import sox_flex_rows

class TestSoxFlex(unittest.TestCase):
    def test_valid(self):
        row=sox_flex_rows({"available":True,"close_date":"2026-11-23","close":9589.096,"change_pct":0.94},"2026-11-24")
        self.assertIn("9,589.10",row["text"])
        self.assertIn("+0.94%",row["text"])
        self.assertIn("2026-11-23",row["text"])
    def test_missing(self):
        self.assertIn("暫不可用",sox_flex_rows({"available":False},"2026-11-24")["text"])
    def test_stale(self):
        self.assertIn("暫不可用",sox_flex_rows({"available":True,"close_date":"2026-11-10","close":9000,"change_pct":1},"2026-11-24")["text"])

if __name__=="__main__":unittest.main()
