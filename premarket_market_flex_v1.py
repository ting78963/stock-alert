# -*- coding: utf-8 -*-
"""08:55 premarket LINE Flex: one white briefing card, no network/sending."""
BG="#FFFFFF"
PANEL="#F5F6F7"
WHITE="#202428"
MUTED="#646970"
GREEN="#18734F"
RED="#A01928"
AMBER="#E68A24"
ORANGE="#E68A24"
DIVIDER="#E1E3E6"
INDICATORS=(
    ("usdtwd","美元／台幣","08:55 最新可用匯率｜須附報價時間"),
    ("sox","費城半導體 SOX","最近美股交易日收盤"),
    ("taiex","臺灣加權指數","前一臺股交易日收盤"),
    ("tx","臺指期貨","08:55 最新可用日盤行情｜須附報價時間"),
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
    lines=[txt(title,"xs",MUTED),txt(value if has_value else "待取得","xl",WHITE,"bold")]
    change=item.get("change")
    if has_value and change is not None and str(change).strip():
        lines.append(txt(change,"xs",(GREEN if key=="usdtwd" else RED) if str(change).lstrip().startswith("+") else (RED if key=="usdtwd" else GREEN) if str(change).lstrip().startswith(("-", "−")) else MUTED))
    if item.get("previous_close") is not None:
        lines.append(txt("前收 "+str(item["previous_close"]),"xs",MUTED))
    lines.append(txt(item.get("timestamp") or subtitle,"xxs",MUTED))
    return {"type":"box","layout":"vertical","backgroundColor":PANEL,"cornerRadius":"12px",
            "paddingAll":"12px","flex":1,"spacing":"sm","contents":lines}

def trend_color(value):
    value=str(value or "")
    if value.startswith("接近") or any(s in value for s in ("放緩","轉換","整理","反彈","回檔","待確認","準備交叉")):
        return AMBER
    if "多頭" in value or "偏多" in value or "黃金交叉" in value or "走強" in value:
        return RED
    if "空頭" in value or "偏空" in value or "死亡交叉" in value or "轉弱" in value:
        return GREEN
    return MUTED

def ma_arrow(n, direction, invert=False):
    up=direction in ("上揚","up","↑")
    down=direction in ("下彎","down","↓")
    color=(GREEN if invert else RED) if up else (RED if invert else GREEN) if down else MUTED
    return txt(f"{n}MA "+("↑" if up else "↓" if down else "→" if direction in ("持平","flat") else "待確認"),"xs",color,"bold")

def rich(parts,size="sm"):
    return {"type":"text","size":size,"weight":"bold","wrap":True,"contents":[{"type":"span","text":str(t),"color":c} for t,c in parts]}

def horizontal(contents):
    return {"type":"box","layout":"horizontal","spacing":"sm","contents":contents}

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
    trend_tiles=[]
    for label,key in (("日線","daily"),
                      ("週線","weekly")):
        item=trend.get(key) or {}
        state=item.get("label") or "資料不足"
        cross=item.get("cross") or "待判斷"
        trend_tiles.append({"type":"box","layout":"vertical","flex":1,"backgroundColor":PANEL,"cornerRadius":"8px","paddingAll":"8px","spacing":"xs","contents":[
            txt(label,"xs",MUTED),
            rich([(p if i==0 else "・"+p,trend_color(p)) for i,p in enumerate(state.replace("｜","・").split("・"))]),
            horizontal([ma_arrow(20,item.get("ma20_direction")),ma_arrow(100,item.get("ma100_direction"))]),
            *([txt(cross.replace("接近","準備") if cross.startswith("接近") else cross+" Day1","xs",trend_color(cross),"bold")] if cross.startswith(("接近","準備")) or cross in ("黃金交叉","死亡交叉") else [])]})
    result.append({"type":"box","layout":"horizontal","spacing":"sm","contents":trend_tiles})
    water=trend.get("waterline") or {}
    if water.get("status")=="ok":
        names={5:"日5MA",10:"日10MA",20:"日20MA",100:"日100MA","week20":"週20MA"}
        events="、".join(names[n]+v for n,v in water["events"].items()) or "無新突破或跌破"
        caps="、".join(f"{names[n]}失守，上限{v}%" for n,v in water["caps"].items()) or "無額外風險限制"
        result.extend([
            txt("持股水位配置","md",WHITE,"bold"),
            horizontal([{"type":"box","layout":"vertical","contents":[txt("建議持股","xs",MUTED),txt(f"{water['target']}%","xxl",RED,"bold")]},{"type":"box","layout":"vertical","contents":[txt("保留現金","xs",MUTED,align="end"),txt(f"{water['cash']}%","xxl",WHITE,"bold",align="end")]}]),
            {"type":"box","layout":"horizontal","height":"10px","cornerRadius":"5px","contents":[
                {"type":"box","layout":"vertical","flex":water["target"],"backgroundColor":RED,"contents":[]},
                {"type":"box","layout":"vertical","flex":water["cash"],"backgroundColor":"#E5E7EB","contents":[]}]},
            txt(f"{water['action']}","sm",AMBER,"bold"),
            horizontal([txt(f"原持股水位 {water['target']-water['delta']}%","xs",MUTED),txt(f"本次調整 {water['delta']:+d}%","xs",MUTED,align="end")]),
            {"type":"box","layout":"horizontal","spacing":"xs","contents":[
                {"type":"box","layout":"vertical","flex":1,"backgroundColor":PANEL,"cornerRadius":"6px","paddingAll":"5px","contents":[txt(f"{n}MA","xs",MUTED,align="center"),txt("碰觸" if n in water.get("touching",[]) else "站上" if water["above"][n] else "跌破","xs",AMBER if n in water.get("touching",[]) else RED if water["above"][n] else GREEN,align="center")]} for n in (5,10,20,100)]},
            txt(events+"；"+caps,"xs",MUTED),
            txt("增碼確認：須同時站上5MA及10MA" if not (water["above"][5] and water["above"][10]) else "短線雙門檻已確認，仍受中長期上限限制","xs",MUTED)])
    elif water:
        result.append(txt("持股水位待確認｜不產生新調整建議","sm",AMBER))
    seasonal=water.get("seasonal_bias") or {}
    if seasonal.get("status")=="ok":
        labels={"normal":("正常區間",MUTED),"early":("初步警戒｜留意追高風險",AMBER),
                "high":("高度警戒｜留意回檔",ORANGE),"extreme":("極端警戒｜市場過熱",RED),
                "negative":("負乖離過大｜留意反彈，不代表落底",GREEN)}
        note,color=labels[seasonal["level"]]
        result.append(txt(f"季線乖離率 {seasonal['bias']:+.2f}%","lg",GREEN if seasonal["bias"]<0 else RED,"bold"))
        result.append(txt(note,"sm",AMBER if seasonal["level"]=="negative" else color,"bold"))
    elif seasonal:
        result.append(txt("季線乖離率｜資料不足","xs",MUTED))
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
        {"type":"box","layout":"horizontal","contents":[txt("↗ MORNING BRIEF","xs",RED,"bold",flex=3),txt("辨識系統","xs",MUTED,align="end",flex=2)]},
        {"type":"box","layout":"horizontal","contents":[txt("開盤前戰情簡報","lg",WHITE,"bold",flex=3),txt(system_status,"xxs",status_color,align="end",flex=2)]},
        txt(observed_at,"xs",MUTED),
        {"type":"separator","margin":"lg","color":DIVIDER},
        *trend_section(trend),
        {"type":"separator","margin":"lg","color":DIVIDER},
        txt("02 · GLOBAL MARKET & FUTURES","xs",MUTED),
        txt("四大市場動態","md",WHITE),
        {"type":"box","layout":"vertical","spacing":"sm","contents":rows},
        {"type":"separator","margin":"lg","color":DIVIDER},
        txt("03 · MARKET OUTLOOK","xs",MUTED),
        txt("今日市場多空研判","md",WHITE),
        
        {"type":"box","layout":"vertical","backgroundColor":PANEL,
         "cornerRadius":"12px","paddingAll":"12px","contents":[
            rich([("趨勢"+str((trend or {}).get("price_regime") or "待確認")+"：",trend_color((trend or {}).get("price_regime"))),(outlook or "待評估",trend_color(outlook))],"xl"),
            txt(observation or "觀察美股、臺指期、匯率及前日台股趨勢，綜合判斷今日市場偏多、偏空或中性。","sm",MUTED)]},
        horizontal([txt("行情依各項報價時間為準","xxs",MUTED),txt("Trade Smart | Your Edge","xxs",MUTED,align="end")])
    ]
    return {"type":"flex","altText":"08:55 開盤前戰情簡報｜四項市場資訊",
            "contents":{"type":"bubble","size":"mega","body":{
                "type":"box","layout":"vertical","backgroundColor":BG,
                "borderColor":"#E5E7EB","borderWidth":"1px","cornerRadius":"12px",
                "paddingAll":"12px","spacing":"sm","contents":body}}}
