# -*- coding: utf-8 -*-
"""A-only VCP FLEX presentation. Reuses the approved B v3 bubble structure.

No sending, trading decision or A->B handoff is performed here.
"""
from __future__ import annotations
import copy
from line_signal_notifier_v3 import build_flex, C_MUTED, C_BORDER, C_TEXT

ORANGE = "#E87900"
ORANGE_DARK = "#C65D00"
RED = "#B4232C"


def _text(value, *, color=C_TEXT, size="sm", weight=None):
    node = {"type": "text", "text":str(value), "size":size, "color":color, "wrap":True}
    if weight:
        node["weight"] = weight
    return node


def build_vcp_flex(event):
    """Return a LINE Flex message for a confirmed A VCP breakout.

    Required fields: stock_id, name, pivot, price, date, recognition_time.
    Additional optional fields: change_pct, vol_ratio, volume_zhang,
    osc_label, indicator_labels. Never invent unavailable indicators.
    """
    for key in ("stock_id", "name", "pivot", "price", "date", "recognition_time"):
        if event.get(key) is None or str(event[key]).strip() == "":
            raise ValueError(f"VCP FLEX missing {key}")
    pivot = float(event["pivot"])
    price = float(event["price"])
    if pivot <= 0 or price <= 0:
        raise ValueError("VCP FLEX requires positive pivot and price")
    # Derive from the existing approved v3 template, not a separate visual system.
    base = build_flex({
        "signal_class":"A", "stock_id":str(event["stock_id"]),
        "stock_name":str(event["name"]),
        "recognition_time":str(event["recognition_time"]),
        "recognition_source":"VCP",
    })
    result = copy.deepcopy(base)
    contents = result["contents"]["body"]["contents"]
    contents[0]["contents"][0]["text"] = "◆"
    contents[0]["contents"][0]["color"] = ORANGE
    contents[0]["contents"][1]["text"] = "VCP SIGNAL"
    contents[0]["contents"][1]["color"] = ORANGE
    contents[0]["contents"][3]["text"] = "突破確認"
    contents[3]["contents"][0]["text"] = "VCP"
    contents[3]["contents"][0]["size"] = "lg"
    contents[3]["contents"][0]["color"] = ORANGE
    contents[3]["contents"][1]["color"] = ORANGE
    contents[3]["contents"][2]["text"] = "型態突破"
    contents[3]["contents"][2]["color"] = ORANGE
    # Replace B-only historical return statistics with actual A snapshot values.
    del contents[5:]
    contents.extend([
        _text("股價觸及 VCP 整理型態關鍵突破價位。", color=C_MUTED),
        {"type":"separator","color":C_BORDER,"margin":"xl"},
        {"type":"box","layout":"horizontal","spacing":"sm","margin":"lg","contents":[
            {"type":"box","layout":"vertical","flex":1,"backgroundColor":"#FFF5EA",
             "cornerRadius":"lg","paddingAll":"md","contents":[
                _text("突破門檻 · Pivot",color=ORANGE_DARK,size="xs"),
                _text(f"{pivot:g} 元",color=ORANGE_DARK,size="xl",weight="bold")]},
            {"type":"box","layout":"vertical","flex":1,"backgroundColor":"#FFF0DD",
             "cornerRadius":"lg","paddingAll":"md","contents":[
                _text("目前成交價",color=ORANGE_DARK,size="xs"),
                _text(f"{price:g} 元",color=ORANGE_DARK,size="xl",weight="bold")]},
        ]},
        {"type":"box","layout":"vertical","backgroundColor":"#FFF3E6",
         "cornerRadius":"md","paddingAll":"md","margin":"sm","contents":[
            _text("↗ 已突破 Pivot" if price > pivot else
                  ("＝ 位於突破門檻" if price == pivot else "↘ 回落至突破價下方"),
                  color=ORANGE_DARK if price > pivot else RED,weight="bold"),
            _text(f"{price-pivot:+.2f} 元  ({(price-pivot)/pivot*100:+.2f}%)",
                  color=ORANGE_DARK if price > pivot else RED,weight="bold"),
        ]},
    ])
    details = []
    for key,label,suffix in (("change_pct","漲跌幅","%"),("vol_ratio","量比","x"),("volume_zhang","目前成交量"," 張")):
        if event.get(key) is not None:
            details.append(_text(f"{label}：{event[key]}{suffix}",color=RED,weight="bold"))
    contents.extend(details)
    if event.get("osc_label"):
        contents.append(_text(str(event["osc_label"]),color=RED,weight="bold"))
    for label in event.get("indicator_labels") or []:
        contents.append(_text(str(label),color=RED,weight="bold"))
    contents.extend([
        {"type":"box","layout":"vertical","backgroundColor":ORANGE_DARK,"cornerRadius":"lg",
         "paddingAll":"md","margin":"xl","contents":[
            {"type":"text","text":"◆  VCP 突破確認","size":"md","weight":"bold","color":"#FFFFFF","align":"center"}]},
        _text(f"◷  VCP 辨識成立  {str(event['recognition_time'])[:5]}",color=C_MUTED),
        {"type":"separator","color":C_BORDER,"margin":"xl"},
        {"type":"box","layout":"horizontal","contents":[
            {"type":"text","text":"辨識訊號・僅供參考","size":"xxs","color":C_MUTED,"flex":1},
            {"type":"text","text":"Trade Smart | Your Edge","size":"xxs","color":C_MUTED,"align":"end","flex":1}]}
    ])
    result["altText"] = f"VCP 突破｜{event['name']} {event['stock_id']}｜Pivot {pivot:g}"
    return result
