import unittest
from research.premarket_sox_brief_section_v1 import build_sox_brief_section

class TestSoxBrief(unittest.TestCase):
    def test_fetch_and_format(self):
        row=build_sox_brief_section("2026-11-24",lambda:{"available":True,"close_date":"2026-11-23","close":9589.096,"change_pct":0.94})
        self.assertIn("9,589.10",row["text"])
    def test_fetch_exception_does_not_break_brief(self):
        def failed(): raise TimeoutError("SOX unavailable")
        self.assertIn("暫不可用",build_sox_brief_section("2026-11-24",failed)["text"])

if __name__=="__main__":unittest.main()
