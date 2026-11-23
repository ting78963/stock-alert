# -*- coding: utf-8 -*-
"""Research-only complete 08:55 LINE Flex assembly.

Caller supplies verified quotes; no network, no send, no scheduler and no A/B changes.
Unknown quotes must remain explicitly unavailable rather than silently fabricated.
"""
from research.taiex_premarket_flex_v1 import taiex_trend_flex_box


def _quote_line(label, quote):
    if not isinstance(quote, dict) or quote.get("value") is None:
        return f"{label}：資料暫缺"
    value = quote["value"]
    as_of = quote.get("as_of")
    source = quote.get("source")
    if not as_of or not source:
        return f"{label}：資料暫缺（缺少時間或來源）"
    return f"{label}：{value}｜{as_of}｜{source}"


def premarket_flex(rows, as_of, quotes):
    """quotes keys: tx, usdtwd, taiex, sox; each has value/as_of/source."""
    lines = [
        _quote_line("台指期 TX", quotes.get("tx")),
        _quote_line("美元／台幣", quotes.get("usdtwd")),
        _quote_line("加權指數", quotes.get("taiex")),
        _quote_line("費城半導體 SOX", quotes.get("sox")),
    ]
    quote_box = {
        "type": "box", "layout": "vertical", "spacing": "sm",
        "contents": [
            {"type": "text", "text": "盤前市場資訊", "weight": "bold", "color": "#8BC5FF", "size": "md"},
            *[{"type": "text", "text": s, "size": "xs", "color": "#FFFFFF", "wrap": True} for s in lines],
        ],
    }
    return {
        "type": "bubble", "size": "mega",
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#10243F",
            "paddingAll": "lg", "spacing": "lg",
            "contents": [
                {"type": "text", "text": f"08:55 台股盤前資訊｜{as_of}",
                 "color": "#FFFFFF", "weight": "bold", "size": "md", "wrap": True},
                quote_box,
                {"type": "separator", "color": "#52647B"},
                taiex_trend_flex_box(rows, as_of),
            ],
        },
    }
