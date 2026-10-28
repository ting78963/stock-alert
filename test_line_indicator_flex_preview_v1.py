"""Production BUY card preview tests; no statistics notifier dependency."""
import unittest
from copy import deepcopy
from abc_buy_flex import abc_buy_flex
from line_indicator_flex_preview_v1 import enrich_preview

class PreviewTests(unittest.TestCase):
    def test_all_buy_signal_classes(self):
        for cls in ("P1", "A", "B", "C"):
            with self.subTest(signal_class=cls):
                event = {"date": "2026-10-26", "stock_id": "1301",
                         "stock_name": "台塑", "signal_class": cls,
                         "recognition_time": "09:32:00"}
                before_event = deepcopy(event)
                original = abc_buy_flex(event)
                original_snapshot = deepcopy(original)
                enriched = enrich_preview(original, {
                    "osc": 0.4, "osc_delta": 0.2,
                    "weekly_kd": "golden_cross",
                    "ma_cross_day": 1, "strong_buy": True})
                self.assertEqual(event, before_event)
                self.assertEqual(original, original_snapshot)
                self.assertEqual(enriched["altText"], original["altText"])
                old = original["contents"]["body"]["contents"]
                new = enriched["contents"]["body"]["contents"]
                self.assertEqual(len(new), len(old) + 1)
                panel = next(x for x in new if x.get("type") == "box"
                             and any("OSC" in str(t.get("text", ""))
                                     for t in x.get("contents", [])))
                self.assertTrue(any("強勢買進" in x["text"]
                                    for x in panel["contents"]))
                self.assertEqual([x for x in new if x is not panel], old)

    def test_no_indicators_keeps_original(self):
        event = {"stock_id": "1301", "signal_class": "A",
                 "recognition_time": "09:32:00"}
        original = abc_buy_flex(event)
        self.assertEqual(enrich_preview(original, {}), original)
        self.assertEqual(enrich_preview(original, {
            "osc": None, "strong_buy": False}), original)

if __name__ == "__main__":
    unittest.main()
