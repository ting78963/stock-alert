"""Preview-only augmentation of existing P1/A/B/C Flex card.

No I/O, no sends, no changes to signal event or retry identity.
Call enrich_preview(base_flex, indicators) on a copy of the original card.
"""
from copy import deepcopy

ORANGE="#E67E22"
GRAY="#8A8F98"
RED="#DC2626"
GREEN="#16A34A"

def _text(value,color=ORANGE):
    return {"type":"text","text":value,"size":"xs","weight":"bold",
            "color":color,"wrap":True,"margin":"sm"}

def indicator_lines(indicators):
    """Only render computed, non-null values. Do not imply missing data is zero."""
    if not isinstance(indicators,dict):return []
    result=[]
    osc=indicators.get("osc")
    if isinstance(osc,(float,int)) and not isinstance(osc,bool):
        delta=indicators.get("osc_delta")
        arrow="━" if delta is None or delta==0 else ("▲" if delta>0 else "▼")
        color=GRAY if delta is None or delta==0 else (RED if delta>0 else GREEN)
        result.append(_text(f"OSC {osc:+.2f} {arrow}（盤中估算）",color))
    wk=indicators.get("weekly_kd")
    if wk=="prepare":result.append(_text("週KD✦ 準備黃金交叉"))
    elif wk=="golden_cross":result.append(_text("週KD✦ 黃金交叉"))
    ma=indicators.get("ma_cross_day")
    if ma in (1,2,3,4,5):result.append(_text(f"5、20MA✦ 黃金交叉 Day{ma}"))
    elif indicators.get("ma_prepare") is True:result.append(_text("5、20MA✦ 準備交叉"))
    if indicators.get("ma20_first_above") is True:
        result.append(_text("20MA✦ 今日站上"))
    if indicators.get("strong_buy") is True:
        result.append(_text("🔥 強勢買進訊號 🔥"))
    return result

def enrich_preview(base_flex,indicators):
    """Insert in SAME card immediately above existing buy action; preserve all else."""
    flex=deepcopy(base_flex)
    body=flex["contents"]["body"]["contents"]
    lines=indicator_lines(indicators)
    if not lines:return flex
    target=next((i for i,x in enumerate(body)
                 if x.get("type")=="box" and x.get("backgroundColor")=="#981B25"),None)
    if target is None:raise ValueError("existing buy action not found; no enrichment")
    panel={"type":"box","layout":"vertical","margin":"lg","contents":lines}
    body.insert(target,panel)
    return flex
