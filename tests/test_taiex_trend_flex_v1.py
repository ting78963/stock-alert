# -*- coding: utf-8 -*-
"""Regression checks for TAIEX narrative and single-message Flex."""
import unittest
from taiex_trend_narrative_v1 import _state
from premarket_market_flex_v1 import build_premarket_flex, RED, GREEN, AMBER

class MarketTrendFlexTests(unittest.TestCase):
    def test_near_cross_only_when_converging(self):
        flat=[100.0]*102
        self.assertEqual(_state(flat)["cross"],"無新交叉")
        self.assertEqual(_state([100.0]*102+[100.01])["cross"],"黃金交叉")

    def test_no_cross_on_parallel_lines(self):
        state=_state([100.0]*120)
        self.assertEqual(state["cross"],"無新交叉")
        self.assertEqual(state["structure"],"交會")

    def test_bullish_weakening_is_not_bearish(self):
        # The short average is above the long one but has started falling.
        values=[100.0]*110+[130.0]*20+[129.0]*2
        state=_state(values)
        self.assertEqual(state["structure"],"偏多")

    def test_flex_is_one_message_with_three_sections(self):
        trend={"headline":"多頭趨勢維持",
               "explanation":"週線偏多",
               "daily":{"label":"偏多、走強","cross":"黃金交叉"},
               "weekly":{"label":"偏空、轉弱","cross":"死亡交叉"}}
        message=build_premarket_flex({},trend=trend,outlook="中性偏多")
        self.assertEqual(message["type"],"flex")
        self.assertEqual(message["contents"]["type"],"bubble")
        import json
        rendered=json.dumps(message,ensure_ascii=False)
        for section in ("01 · TAIEX","02 · GLOBAL","03 · MARKET"):
            self.assertIn(section,rendered)
        self.assertIn(RED,rendered)
        self.assertIn(GREEN,rendered)
        self.assertIn("待取得",rendered)

    def test_price_signs_use_taiwan_market_colors(self):
        message=build_premarket_flex({"sox":{"value":"100","change":"+1%"},
                                      "tx":{"value":"100","change":"−1%"}})
        import json
        rendered=json.dumps(message,ensure_ascii=False)
        self.assertIn('"text": "+1%", "size": "xs", "color": "'+RED+'"',rendered)
        self.assertIn('"text": "−1%", "size": "xs", "color": "'+GREEN+'"',rendered)

if __name__=="__main__":
    unittest.main()
