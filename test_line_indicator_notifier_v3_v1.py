"""Tests for production LINE notifier v3 card path (no actual send)."""
import ast
import io
import json
import sys
import types
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
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
    def test_actual_main_dryrun_success_and_indicator_failure(self):
        import line_indicator_snapshot_v1 as snapshot
        e={"stock_id":"1301","stock_name":"台塑","signal_class":"A",
           "recognition_time":"09:31:00","date":"2026-10-26"}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"event.json"
            path.write_text(json.dumps(e),encoding="utf-8")
            minute_dir=Path(d)/"b_live_runner_v2_p1"/"2026-10-26"/"1301"
            minute_dir.mkdir(parents=True)
            (minute_dir/"canonical_minutes.jsonl").write_text(
                json.dumps({"date":"2026-10-26","minute":"09:31:00","open":10,"high":11,"low":10,"close":11})+"\n",encoding="utf-8")
            for indicator,expected in [({"osc":0.5,"osc_delta":0.2},"OSC"),
                                       (RuntimeError("missing history"),"LINE INDICATOR SKIP")]:
                with self.subTest(expected=expected):
                    output=io.StringIO()
                    with patch.object(sys,"argv",["notifier",str(path),"--preview-json"]), \
                         patch.object(notifier,"load_event",return_value=e.copy()), \
                         patch.dict("os.environ",{"PRODUCTION_STATE_DIR":d}), \
                         patch.object(snapshot,"compute_indicators",side_effect=indicator if isinstance(indicator,Exception) else None,return_value=indicator if isinstance(indicator,dict) else None), \
                         patch.object(notifier,"send",side_effect=AssertionError("must not send")), \
                         redirect_stdout(output):
                        notifier.main()
                    self.assertIn(expected,output.getvalue())
                    self.assertIn("DRY RUN PASS",output.getvalue())
                    self.assertNotIn("line_sent",path.read_text(encoding="utf-8"))
    def test_main_filters_future_minutes_before_snapshot(self):
        import line_indicator_snapshot_v1 as snapshot
        e={"stock_id":"1301","stock_name":"台塑","signal_class":"A",
           "recognition_time":"09:31:00","date":"2026-10-26"}
        captured=[]
        bars=[{"date":"2026-10-26","minute":t,"open":10,"high":11,"low":10,"close":11} for t in ("09:30:00","09:31:00","09:32:00")]
        def compute(symbol,day,minutes,cutoff):
            captured.extend(minutes)
            return {}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"event.json"
            path.write_text("{}",encoding="utf-8")
            minute_dir=Path(d)/"b_live_runner_v2_p1"/"2026-10-26"/"1301"
            minute_dir.mkdir(parents=True)
            (minute_dir/"canonical_minutes.jsonl").write_text(
                "".join(json.dumps(b)+"\n" for b in bars),encoding="utf-8")
            with patch.object(sys,"argv",["notifier",str(path)]), \
                 patch.object(notifier,"load_event",return_value=e), \
                 patch.dict("os.environ",{"PRODUCTION_STATE_DIR":d}), \
                 patch.object(snapshot,"compute_indicators",side_effect=compute), \
                 redirect_stdout(io.StringIO()):
                notifier.main()
        self.assertEqual([r["minute"] for r in captured],["09:30:00","09:31:00"])
    def test_preview_json_contains_real_indicator_panel_in_same_card(self):
        import line_indicator_snapshot_v1 as snapshot
        e={"stock_id":"1301","stock_name":"台塑","signal_class":"B",
           "recognition_time":"09:31:00","date":"2026-10-26"}
        indicators={"osc":0.58,"osc_delta":0.21,"weekly_kd":"prepare",
                    "ma_cross_day":2,"ma_prepare":False,
                    "ma20_first_above":True,"strong_buy":True}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"event.json"
            path.write_text("{}",encoding="utf-8")
            minute_dir=Path(d)/"b_live_runner_v2_p1"/"2026-10-26"/"1301"
            minute_dir.mkdir(parents=True)
            (minute_dir/"canonical_minutes.jsonl").write_text(
                json.dumps({"date":"2026-10-26","minute":"09:31:00","open":10,
                            "high":11,"low":10,"close":11})+"\n",encoding="utf-8")
            output=io.StringIO()
            with patch.object(sys,"argv",["notifier",str(path),"--preview-json"]), \
                 patch.object(notifier,"load_event",return_value=e), \
                 patch.dict("os.environ",{"PRODUCTION_STATE_DIR":d}), \
                 patch.object(snapshot,"compute_indicators",return_value=indicators), \
                 patch.object(notifier,"send",side_effect=AssertionError("must not send")), \
                 redirect_stdout(output):
                notifier.main()
            out=output.getvalue()
            self.assertIn("OSC +0.58",out)
            self.assertIn("週KD",out)
            self.assertIn("黃金交叉 Day2",out)
            self.assertIn("20MA",out)
            self.assertIn("強勢買進訊號",out)
            self.assertIn("立即買進",out)
            self.assertIn("DRY RUN PASS",out)
            self.assertNotIn("line_sent",path.read_text(encoding="utf-8"))
    def test_production_runner_targets_notifier_v3(self):
        source=(ROOT/"fugle_b_live_runner_v2_p1_final.py").read_text(encoding="utf-8")
        self.assertIn('NOTIFIER=BASE/"line_signal_notifier_v3.py"',source)
        self.assertIn('str(NOTIFIER)',source)
if __name__=="__main__":unittest.main()
