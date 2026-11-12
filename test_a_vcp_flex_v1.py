# -*- coding: utf-8 -*-
"""Offline regression checks: approved B card stays unchanged; VCP is presentation-only."""
import copy
import unittest
from a_vcp_flex_v1 import build_vcp_flex
from line_signal_notifier_v3 import build_flex


class VcpFlexTests(unittest.TestCase):
    def setUp(self):
        self.e = dict(stock_id="6150", name="測試股票", date="2026-11-12",
                      recognition_time="09:26:00", pivot=77.5, price=78.4,
                      change_pct=1.82, vol_ratio=2.66, volume_zhang=8824,
                      osc_label="OSC +0.70 ▲",
                      indicator_labels=["週KD✦ 黃金交叉", "5、20MA✦ 黃金交叉 day1"])

    def test_vcp_pivot_price_and_delta(self):
        card = build_vcp_flex(self.e)
        body = card["contents"]["body"]["contents"]
        data = str(body)
        self.assertIn("77.5 元", data)
        self.assertIn("78.4 元", data)
        self.assertIn("+0.90 元", data)
        self.assertIn("+1.16%", data)
        self.assertIn("#E87900", data)
        self.assertIn("週KD✦ 黃金交叉", data)
        self.assertNotIn("立即買進", data)

    def test_b_original_is_unchanged(self):
        e = dict(signal_class="A", stock_id="6150", stock_name="測試股票",
                 recognition_time="09:26:00", recognition_source="VCP")
        before = copy.deepcopy(build_flex(e))
        build_vcp_flex(self.e)
        self.assertEqual(before, build_flex(e))
        self.assertIn("立即買進", str(before))

    def test_below_pivot_not_called_breakout(self):
        self.e["price"] = 76.5
        text = str(build_vcp_flex(self.e))
        self.assertIn("回落至突破價下方", text)
        self.assertNotIn("↗ 已突破 Pivot", text)

    def test_missing_pivot_fails_closed(self):
        self.e.pop("pivot")
        with self.assertRaises(ValueError):
            build_vcp_flex(self.e)


if __name__ == "__main__":
    unittest.main()
