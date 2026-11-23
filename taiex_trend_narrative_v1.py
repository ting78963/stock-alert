# -*- coding: utf-8 -*-
"""Deterministic TAIEX MA20/MA100 regime and crossover narrative; no side effects."""
from taiex_market_history_v1 import normalize_daily, completed_week_closes

def _ma(values, n, offset=0):
    end=len(values)-offset
    return sum(values[end-n:end])/n if end>=n else None

def _state(closes, near_threshold=0.005):
    if len(closes)<102:
        return {"label":"資料不足","structure":None,"momentum":None,"cross":"無法判斷"}
    short,long=_ma(closes,20),_ma(closes,100)
    ps,pl=_ma(closes,20,1),_ma(closes,100,1)
    spread=(short-long)/long
    prior=(ps-pl)/pl
    structure="偏多" if spread>0 else "偏空" if spread<0 else "交會"
    ss=(short-ps)/ps
    ls=(long-pl)/pl
    if ss>0.0001 and ls>=-0.0001:
        momentum="走強"
    elif ss< -0.0001 and ls<=0.0001:
        momentum="轉弱"
    else:
        momentum="整理"
    if prior<=0 and spread>0:
        cross="黃金交叉"
    elif prior>=0 and spread<0:
        cross="死亡交叉"
    elif 0<abs(spread)<=near_threshold and abs(spread)<abs(prior):
        cross="接近黃金交叉" if spread<0 else "接近死亡交叉"
    else:
        cross="無新交叉"
    return {"label":structure+"、"+momentum,"structure":structure,
            "momentum":momentum,"cross":cross,
            "ma20":round(short,2),"ma100":round(long,2)}

def analyze_taiex(rows,as_of):
    """Report on as_of morning: exclude as_of daily bar and unfinished weekly bar."""
    daily=[r for r in normalize_daily(rows) if r["date"]<str(as_of)[:10]]
    weekly=completed_week_closes(daily,as_of)
    d=_state([r["close"] for r in daily])
    w=_state([r["close"] for r in weekly])
    if d["structure"] is None or w["structure"] is None:
        return {"headline":"資料不足","daily":d,"weekly":w,
                "explanation":"歷史收盤資料尚未補齊，暫不判斷大盤趨勢。"}
    if w["structure"]=="偏多":
        headline="多頭仍在，但漲勢放緩" if d["momentum"]=="轉弱" or d["structure"]=="偏空" else "多頭趨勢維持"
    elif w["structure"]=="偏空":
        headline="空頭仍在，短線出現改善" if d["momentum"]=="走強" else "空頭趨勢持續"
    else:
        headline="多空轉換期"
    crosses=[f"{period}{part['cross']}" for period,part in (("日線",d),("週線",w))
             if part["cross"] not in ("無新交叉","無法判斷")]
    explanation=(f"短期日線{d['label']}；中長期週線{w['label']}。"
                 +(f"轉折觀察：{'、'.join(crosses)}。" if crosses else "目前沒有新的均線交叉訊號。"))
    return {"headline":headline,"daily":d,"weekly":w,"explanation":explanation}
