# -*- coding: utf-8 -*-
"""08:55 premarket LINE Flex: one dark-navy briefing card, no network/sending."""
BG="#101c2e"
PANEL="#1d2d45"
WHITE="#f3f6fc"
MUTED="#a3b3c9"
GREEN="#63d4a6"
RED="#ff6868"
AMBER="#ffc65a"
DIVIDER="#34465f"
INDICATORS=(
    ("usdtwd","美元／台幣","USD/TWD"),
    ("sox","費城半導體 SOX","前一交易日"),
    ("taiex","臺灣加權指數","前一交易日"),
    ("tx","臺指期貨","最近可用行情（非當日日盤）"),
)

def txt(s,size="sm",color=WHITE,weight=None,**kwargs):
    result={"type":"text","text":str(s),"size":size,"color":color,"wrap":True}
    if weight: result["weight"]=weight
    result.update(kwargs)
    return result

def panel(key,title,subtitle,data):
    item=data.get(key) or {}
    value=item.get("value")
    has_value=value is not None and str(value).strip()!=""
    lines=[txt(title,"xs",MUTED),txt(value if has_value else "待取得","sm",WHITE,"bold")]
    change=item.get("change")
    if has_value and change is not None and str(change).strip():
        lines.append(txt(change,"xs",RED if str(change).lstrip().startswith("+") else GREEN if str(change).lstrip().startswith(("-", "−")) else MUTED))
    lines.append(txt(item.get("timestamp") or subtitle,"xxs",MUTED))
    return {"type":"box","layout":"vertical","backgroundColor":PANEL,"cornerRadius":"12px",
            "paddingAll":"12px","flex":1,"spacing":"sm","contents":lines}

def trend_color(value):
    value=str(value or "")
    if value.startswith("接近") or "放緩" in value or "轉換" in value:
        return AMBER
    if "多頭" in value or "偏多" in value or "黃金交叉" in value or "走強" in value:
        return RED
    if "空頭" in value or "偏空" in value or "死亡交叉" in value or "轉弱" in value:
        return GREEN
    return MUTED

def trend_section(trend):
    trend=trend or {}
    headline=trend.get("headline") or "資料待取得"
    result=[txt("01 · TAIEX MARKET TREND","xs",MUTED),
            txt("大盤多空趨勢","md",WHITE,"bold"),
            {"type":"box","layout":"vertical","backgroundColor":PANEL,
             "cornerRadius":"12px","paddingAll":"12px","spacing":"sm",
             "contents":[txt("目前市場階段","xs",MUTED),
                         txt(headline,"lg",trend_color(headline),"bold"),
                         txt(trend.get("explanation") or "大盤歷史資料待補齊。","sm",WHITE)]}]
    for label,key in (("短期 · 日線 MA20 / MA100","daily"),
                      ("中長期 · 週線 MA20 / MA100","weekly")):
        item=trend.get(key) or {}
        state=item.get("label") or "資料不足"
        cross=item.get("cross") or "待判斷"
        result.append({"type":"box","layout":"vertical","spacing":"xs","contents":[
            txt(label,"xs",MUTED),
            txt(state,"sm",trend_color(state),"bold"),
            txt(cross,"xs",trend_color(cross))]})
    return result

def build_premarket_flex(indicators,observed_at="08:55",observation=None,
                         system_status="待確認",system_ok=None,trend=None,outlook=None):
    """Build exactly one LINE Flex message; caller handles market data and delivery.

    indicators: dict of usdtwd/sox/taiex/tx with formatted value/change/timestamp.
    Missing values remain '待取得'; no invented prices or operational status.
    """
    rows=[]
    for start in (0,2):
        rows.append({"type":"box","layout":"horizontal","spacing":"sm","contents":[
            panel(*INDICATORS[i],indicators) for i in range(start,start+2)]})
    status_color=GREEN if system_ok is True else AMBER if system_ok is False else MUTED
    body=[
        txt("STOCK ALERT · MORNING BRIEF","xs",MUTED),
        txt("開盤前戰情簡報","lg",WHITE,"bold"),
        txt(f"{observed_at} · 交易日自動發送","xs",MUTED),
        {"type":"separator","margin":"lg","color":DIVIDER},
        {"type":"box","layout":"horizontal","margin":"lg","contents":[
            {"type":"box","layout":"vertical","flex":1,"contents":[
                txt("辨識系統","xs",MUTED),txt(system_status,"md",status_color,"bold")]},
            {"type":"box","layout":"vertical","flex":1,"contents":[
                txt("三路監控","xs",MUTED,align="end"),
                txt("SURGE / FLOW / VCP","sm",WHITE,"bold",align="end")]}
        ]},
        {"type":"separator","margin":"lg","color":DIVIDER},
        *trend_section(trend),
        {"type":"separator","margin":"lg","color":DIVIDER},
        txt("02 · GLOBAL MARKET & FUTURES","xs",MUTED),
        txt("國際市場、匯率與期貨","md",WHITE),
        {"type":"box","layout":"vertical","spacing":"sm","contents":rows},
        {"type":"separator","margin":"lg","color":DIVIDER},
        txt("03 · MARKET OUTLOOK","xs",MUTED),
        txt("今日市場多空研判","md",WHITE),
        txt(outlook or "待評估","md",trend_color(outlook),"bold"),
        {"type":"box","layout":"vertical","backgroundColor":PANEL,
         "cornerRadius":"12px","paddingAll":"12px","contents":[
            txt(observation or "觀察美股、臺指期、匯率及前日台股趨勢，綜合判斷今日市場偏多、偏空或中性。","sm",MUTED)]},
        txt("示意卡片 · 非即時行情或實際系統健康狀態","xxs",MUTED)
    ]
    return {"type":"flex","altText":"08:55 開盤前戰情簡報｜四項市場資訊",
            "contents":{"type":"bubble","size":"mega","body":{
                "type":"box","layout":"vertical","backgroundColor":BG,
                "paddingAll":"16px","spacing":"md","contents":body}}}
