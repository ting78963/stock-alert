"""Ensure preview preserves original notifier card and signal identity."""
import unittest
from copy import deepcopy
from line_signal_notifier_v3 import build_flex,retry_key
from abc_buy_flex import abc_buy_flex
from line_indicator_flex_preview_v1 import enrich_preview

class PreviewTests(unittest.TestCase):
    def test_all_classes_both_card_paths(self):
        for cls in ("P1","A","B","C"):
            e={"date":"2026-10-26","stock_id":"1301","stock_name":"台塑",
               "signal_class":cls,"recognition_time":"09:32:00"}
            for builder in (build_flex,abc_buy_flex):
                with self.subTest(cls=cls,builder=builder.__name__):
                    original=builder(e)
                    before=deepcopy(original)
                    key=retry_key(e)
                    enriched=enrich_preview(original,{"osc":0.4,"osc_delta":0.2,
                      "weekly_kd":"golden_cross","ma_cross_day":1,"strong_buy":True})
                    self.assertEqual(original,before)
                    self.assertEqual(retry_key(e),key)
                    self.assertEqual(enriched["altText"],original["altText"])
                    old=original["contents"]["body"]["contents"]
                    new=enriched["contents"]["body"]["contents"]
                    self.assertEqual(len(new),len(old)+1)
                    panel=new[next(i for i,x in enumerate(new) if x.get("type")=="box" and x.get("contents") and any("OSC" in str(t.get("text","")) for t in x.get("contents",[])))]
                    self.assertTrue(any("強勢買進" in x["text"] for x in panel["contents"]))
                    self.assertEqual([x for x in new if x is not panel],old)

    def test_no_data_is_identical(self):
        e={"stock_id":"1301","signal_class":"A","recognition_time":"09:32:00"}
        base=build_flex(e)
        self.assertEqual(enrich_preview(base,{}),base)
        self.assertEqual(enrich_preview(base,{"osc":None,"strong_buy":False}),base)

if __name__=="__main__":unittest.main()
