import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
from premarket_taiex_adapter_v1 import build_taiex_preview

TPE=ZoneInfo("Asia/Taipei")

class MorningFxPreviewTests(unittest.TestCase):
    def setUp(self):
        self.report_at=datetime(2026,11,23,8,55,tzinfo=TPE)
        self.rows=[{"date":f"2026-10-{d:02d}","close":32.0+d/100} for d in range(1,21)]
        self.rows.append({"date":"2026-11-20","close":32.936})
        self.quote={"value":33.0,"quoted_at":"2026-11-23T08:54:30+08:00","source":"live_rates","quote_kind":"market_spot"}

    def build(self,quote=None,rows=None):
        with patch("premarket_taiex_adapter_v1.load_taiex_trend",return_value={"as_of":"2026-11-23"}):
            with patch("premarket_taiex_adapter_v1.read_store",return_value=[]):
                return build_taiex_preview(indicators={"usdtwd":self.quote if quote is None else quote},cbc_fx_rows=self.rows if rows is None else rows,report_at=self.report_at)

    def fx_panel(self,card):
        panels=card["contents"]["body"]["contents"]
        for row in panels:
            if row.get("type")=="box" and row.get("layout")=="vertical":
                for child in row.get("contents",[]):
                    if child.get("layout")=="horizontal":
                        for panel in child["contents"]:
                            if panel["contents"][0]["text"]=="美元／台幣":
                                return panel
        for row in panels:
            if row.get("layout")=="horizontal":
                for panel in row.get("contents",[]):
                    if panel.get("contents") and panel["contents"][0].get("text")=="美元／台幣":
                        return panel
        self.fail("USD/TWD panel missing")

    def test_live_fx_shows_cbc_comparison_and_ma(self):
        panel=self.fx_panel(self.build())
        strings=[x["text"] for x in panel["contents"]]
        self.assertTrue(any("臺幣貶值" in x for x in strings))
        self.assertTrue(any("2026-11-20" in x for x in strings))
        self.assertTrue(any("MA5" in x and "MA20" in x for x in strings))
        self.assertTrue(any("不同來源" in x for x in strings))

    def test_stale_fx_never_displays_change(self):
        quote=dict(self.quote,quoted_at="2026-11-23T08:40:00+08:00")
        panel=self.fx_panel(self.build(quote=quote))
        strings=[x["text"] for x in panel["contents"]]
        self.assertIn("待取得",strings)
        self.assertFalse(any("臺幣貶值" in x for x in strings))

if __name__=="__main__":
    unittest.main()
