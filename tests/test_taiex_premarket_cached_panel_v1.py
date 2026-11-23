# -*- coding: utf-8 -*-
"""08:55 cached TAIEX panel: no external data, no invented prices."""
import tempfile
import unittest
from pathlib import Path
from taiex_fugle_store_v1 import write_store
from premarket_taiex_adapter_v1 import build_taiex_preview

def all_text(node):
    if isinstance(node,dict):
        return ([node["text"]] if node.get("type")=="text" else []) + sum((all_text(v) for v in node.values()),[])
    if isinstance(node,list):
        return sum((all_text(v) for v in node),[])
    return []

class CachedPanelTests(unittest.TestCase):
    def test_previous_close_and_change_display(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"taiex.json"
            write_store(path,[{"date":"2026-11-19","close":20000},{"date":"2026-11-20","close":20200}])
            card=build_taiex_preview(as_of="2026-11-23",path=path)
            content=" ".join(all_text(card))
            self.assertIn("20,200.00",content)
            self.assertIn("+200.00 (+1.00%)",content)
            self.assertIn("2026-11-20 收盤",content)
    def test_tx_day_session_opens_before_0855_report(self):
        with tempfile.TemporaryDirectory() as td:
            card=build_taiex_preview(as_of="2026-11-23",path=Path(td)/"missing.json")
            content=" ".join(all_text(card))
            self.assertIn("08:55 最新可用日盤行情｜須附報價時間",content)
            self.assertNotIn("最近可用行情（非當日日盤）",content)

    def test_no_cache_keeps_missing_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            card=build_taiex_preview(as_of="2026-11-23",path=Path(td)/"missing.json")
            content=" ".join(all_text(card))
            self.assertIn("待取得",content)
            self.assertNotIn("20,200.00",content)
if __name__=="__main__":
    unittest.main()
