# -*- coding: utf-8 -*-
"""Research-only 08:55 TAIEX trend section for a dark-blue LINE Flex.

This is a pure formatter: no LINE sends, API calls, scheduling, or A/B changes.
"""
from research.taiex_premarket_ma_v1 import market_trend_snapshot

DIRECTION = {"rising": "↗ 上揚", "falling": "↘ 下彎", "flat": "→ 走平", "insufficient": "資料不足"}
STATUS = {"golden_cross": "黃金交叉", "prepare_golden": "準備黃金交叉",
          "death_cross": "死亡交叉", "prepare_death": "準備死亡交叉",
          "above": "多頭排列", "below": "空頭排列", "equal": "均線重合",
          "insufficient": "資料不足"}


def trend_lines(rows, as_of):
    report = market_trend_snapshot(rows, as_of)
    result = []
    for label, key in (("日線", "daily"), ("週線", "weekly")):
        section = report[key]
        ma20 = section["ma"]["ma20"]
        ma100 = section["ma"]["ma100"]
        cross = section["cross_20_100"]
        if not section["cross_ready"]:
            cross_text = "交叉資料不足"
        else:
            cross_text = STATUS.get(cross["status"], cross["status"])
            golden = cross.get("golden_label", "")
            if golden.startswith("golden_cross_day"):
                cross_text += " Day" + golden.rsplit("day", 1)[1]
        result.extend([
            f"{label} MA20：{ma20['value']:.2f}｜{DIRECTION[ma20['direction']]}" if ma20["value"] is not None else f"{label} MA20：資料不足",
            f"{label} MA100：{ma100['value']:.2f}｜{DIRECTION[ma100['direction']]}" if ma100["value"] is not None else f"{label} MA100：資料不足",
            f"{label} 20/100：{cross_text}",
        ])
    return result


def taiex_trend_flex_box(rows, as_of):
    """LINE Flex box section to embed in the existing 08:55 dark-blue bubble."""
    lines = trend_lines(rows, as_of)
    return {
        "type": "box", "layout": "vertical", "spacing": "sm",
        "contents": [
            {"type": "text", "text": "大盤均線趨勢", "color": "#8BC5FF", "weight": "bold", "size": "md"},
            *[{"type": "text", "text": line, "color": "#FFFFFF", "size": "xs", "wrap": True}
              for line in lines],
        ],
    }
