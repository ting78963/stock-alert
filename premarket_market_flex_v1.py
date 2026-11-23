# -*- coding: utf-8 -*-
"""One 08:55 LINE Flex message for four market indicators.

Pure presentation only: no API calls, scheduling, or LINE sending.
Values are supplied by the market-data layer; unavailable data stays unavailable.
"""
from datetime import datetime

INDICATORS = (
    ("taiex", "臺灣加權指數", "前一交易日收盤"),
    ("tx", "臺指期 TX", "當日日盤即時行情"),
    ("sox", "費城半導體 SOX", "最近美股交易日收盤"),
    ("usdtwd", "美元／新臺幣", "最新可用匯率"),
)


def _txt(value, size="sm", color="#202020", weight=None, flex=None, align=None):
    node = {"type": "text", "text": str(value), "size": size, "color": color, "wrap": True}
    if weight:
        node["weight"] = weight
    if flex is not None:
        node["flex"] = flex
    if align:
        node["align"] = align
    return node


def build_premarket_flex(indicators, observed_at="08:55", observation=None):
    """Return a single LINE Flex message.

    indicators keys: taiex, tx, sox, usdtwd. Each entry may have:
      value (formatted string), change (formatted string), timestamp (display string).
    Never invent a value when its source is missing.
    """
    rows = [
        _txt("MARKET PULSE", "xs", "#888888", "bold"),
        {"type": "box", "layout": "horizontal", "contents": [
            _txt("盤前市場快報", "lg", "#202020", "bold", 1),
            _txt(observed_at, "sm", "#888888", align="end"),
        ]},
        {"type": "separator", "margin": "md", "color": "#eeeeee"},
    ]
    for key, label, description in INDICATORS:
        item = indicators.get(key) or {}
        value = item.get("value")
        valid = value is not None and str(value).strip() != ""
        shown = str(value) if valid else "資料暫缺"
        change = item.get("change") if valid else None
        timestamp = item.get("timestamp")
        detail = description + ((" · " + str(timestamp)) if timestamp else "")
        value_lines = [_txt(shown, "sm", "#202020" if valid else "#999999", "bold", align="end")]
        if change is not None and str(change).strip():
            value_lines.append(_txt(change, "xs", "#777777", align="end"))
        rows.extend([
            {"type": "box", "layout": "horizontal", "margin": "md", "spacing": "sm", "contents": [
                {"type": "box", "layout": "vertical", "flex": 5, "contents": [
                    _txt(label, "sm", "#202020", "bold"),
                    _txt(detail, "xs", "#999999"),
                ]},
                {"type": "box", "layout": "vertical", "flex": 4, "contents": value_lines},
            ]},
            {"type": "separator", "margin": "md", "color": "#f2f2f2"},
        ])
    rows.extend([
        _txt("市場綜合觀察", "sm", "#202020", "bold"),
        _txt(observation or "依最新有效資料觀察市場方向；資料不足時不推測。", "sm", "#666666"),
        _txt("Trade Smart | Your Edge", "xs", "#aaaaaa"),
    ])
    return {
        "type": "flex",
        "altText": "08:55 盤前市場快報｜加權指數、臺指期、費半、美元／新臺幣",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "18px",
                "spacing": "sm", "contents": rows,
            },
        },
    }
