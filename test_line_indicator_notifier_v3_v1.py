"""Tests for production LINE notifier v3 card path (no actual send)."""
import ast
import unittest
from pathlib import Path
import line_signal_notifier_v3 as notifier
from line_indicator_flex_preview_v1 import enrich_preview

ROOT=Path(__file__).parent
class NotifierV3Tests(unittest.TestCase):
    def test_actual_notifier_main_uses_failopen_indicator_enrichment(self):
        tree=ast.parse((ROOT/"line_signal_notifier_v3.py").read_text(encoding="utf-8"))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
        self.assertTrue(any(isinstance(n,ast.Try) and any(
            isinstance(x,ast.Name) and x.id=="enrich_preview" for x in ast.walk(n))
            for n in main.body))
    def test_real_v3_card_preserves_buy_and_fallback(self):
        for cls in ("P1","A","B","C"):
            with self.subTest(cls=cls):
                e={"stock_id":"1301","stock_name":"台塑","signal_class":cls,
                   "recognition_time":"09:31:00","date":"2026-10-26"}
                base=notifier.build_flex(e)
                card=enrich_preview(base,{"osc":0.5,"osc_delta":0.2,"ma20_first_above":True})
                self.assertIn("OSC",str(card))
                self.assertIn("20MA",str(card))
                self.assertEqual(len(card["contents"]["body"]["contents"]),
                                 len(base["contents"]["body"]["contents"])+1)
                self.assertEqual(enrich_preview(base,{}),base)
                self.assertEqual(sum(x.get("backgroundColor")=="#981B25"
                    for x in card["contents"]["body"]["contents"]),1)
    def test_production_runner_targets_notifier_v3(self):
        source=(ROOT/"fugle_b_live_runner_v2_p1_final.py").read_text(encoding="utf-8")
        self.assertIn('NOTIFIER=BASE/"line_signal_notifier_v3.py"',source)
        self.assertIn('str(NOTIFIER)',source)
if __name__=="__main__":unittest.main()
