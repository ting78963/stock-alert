"""Isolated B send-site regression: indicators must never suppress BUY."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).parent
SOURCE=(ROOT/"b_runner.py").read_text(encoding="utf-8")

def send_section():
    tree=ast.parse(SOURCE)
    runner=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_evaluate")
    start=next(i for i,n in enumerate(runner.body)
               if isinstance(n,ast.Assign) and any(
                   isinstance(t,ast.Name) and t.id=="event" for t in n.targets))
    stop=next(i for i,n in enumerate(runner.body[start:],start)
              if isinstance(n,ast.If) and isinstance(n.test,ast.UnaryOp)
              and isinstance(n.test.operand,ast.Name) and n.test.operand.id=="ok")
    # Execute the original AST for the event creation + card assembly + send,
    # with fake send and indicator dependencies, no live network.
    return compile(ast.fix_missing_locations(ast.Module(body=runner.body[start:stop+1],
                                                        type_ignores=[])),"b_runner.py","exec")

class BSendFailOpen(unittest.TestCase):
    def _run(self,indicator):
        from abc_buy_flex import abc_buy_flex
        import line_indicator_snapshot_v1 as snapshot
        import line_indicator_flex_preview_v1 as preview
        posted=[]
        scope=dict(date="2026-10-26",symbol="1301",cls="A",discovered="09:30:00",
                   recognition="09:31:00",live_known="09:31:00",
                   a2={"a2_end":"09:30:00","a2_vr":2.0},vr=2.0,eh=3.0,
                   early={"early_price":100.0},pdate="2026-10-23",
                   _clock=lambda x:str(x)[:8],meta={"name":"台塑"},
                   rows=[],cutoff="09:31:59",line_token="fake",group_id="fake",
                   abc_buy_flex=abc_buy_flex,
                   _post_flex=lambda card,*args: posted.append(card) or True,
                   _lock=__import__("threading").Lock(),_sent=set(),
                   event_id="test-event",STATE_DIR=ROOT)
        with patch.object(snapshot,"compute_indicators",side_effect=indicator):
            exec(send_section(),scope)
        return posted,scope

    def test_indicator_exception_still_posts_original_buy(self):
        from abc_buy_flex import abc_buy_flex
        posted,scope=self._run(RuntimeError("missing history"))
        self.assertEqual(len(posted),1)
        self.assertEqual(posted[0],abc_buy_flex(scope["event"],"台塑"))

    def test_indicator_values_enrich_same_buy_card(self):
        posted,_=self._run({"osc":0.4,"osc_delta":0.2,"weekly_kd":"golden_cross"})
        self.assertEqual(len(posted),1)
        self.assertTrue(any("OSC" in str(x) for x in
                            posted[0]["contents"]["body"]["contents"]))
        self.assertEqual(posted[0]["type"],"flex")

if __name__=="__main__":unittest.main()
