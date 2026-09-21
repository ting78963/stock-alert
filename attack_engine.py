from __future__ import annotations
import pandas as pd

ATTACK_SEARCH_END = "13:30:00"

def _make_bar_dict(time, open_, high, low, close, vol):
    return {"time": time, "open": open_, "high": high, "low": low, "close": close, "volume": vol}

def _build_attack_record(bars, key_price):
    start_bar, end_bar = bars[0], bars[-1]
    attack_high=max(b["high"] for b in bars); attack_low=min(b["low"] for b in bars)
    v1a=bars[0]["volume"]; v1b=sum(b["volume"] for b in bars)
    is_close_above=float(end_bar["close"]) >= key_price
    return {
        "start_time":start_bar["time"],"end_time":end_bar["time"],"bars_used":len(bars),
        "start_price":start_bar["open"],"key_price":key_price,"attack_high":attack_high,"attack_low":attack_low,
        "attack_volume":v1b,"attack_volume_v1a":v1a,"attack_volume_v1b":v1b,
        "is_touch":attack_high>=key_price,"is_upward":True,
        "is_cross":start_bar["low"]<key_price and attack_high>key_price,
        "is_close_above":is_close_above,"crossed_key":attack_high>key_price,
        "closed_above_key":is_close_above,
        "attack_high_above_key":round(attack_high-key_price,2) if attack_high>key_price else 0.0,
        "entry_at_trigger":None,"entry_at_bar_close":float(end_bar["close"]),
        "entry_next_open":None,"entry_next_close":None,"_bars":bars,
    }

def find_attacks(df: pd.DataFrame,key_price:float,key_created_time:str,search_end:str=ATTACK_SEARCH_END,finalize_last:bool=True):
    df_search=df[(df["time_str"]>key_created_time)&(df["time_str"]<=search_end)].copy().reset_index(drop=True)
    if df_search.empty:return []
    before=df[df["time_str"]<=key_created_time]
    prev_close=float(before.iloc[-1]["close"]) if not before.empty else key_price
    attacks=[]; in_attack=False; bars=[]
    for i,row in df_search.iterrows():
        o=float(row["open"] or 0); h=float(row["high"] or 0); l=float(row["low"] or 0); c=float(row["close"] or 0)
        v=int(row["volume"] or 0); t=str(row["time"]); last=i==len(df_search)-1
        if not in_attack:
            if prev_close<key_price and h>=key_price:
                in_attack=True; bars=[_make_bar_dict(t,o,h,l,c,v)]
                if c<key_price or (last and finalize_last):
                    attacks.append(_build_attack_record(bars,key_price)); in_attack=False; bars=[]
        else:
            bars.append(_make_bar_dict(t,o,h,l,c,v))
            if c<key_price or (last and finalize_last):
                attacks.append(_build_attack_record(bars,key_price)); in_attack=False; bars=[]
        prev_close=c
    return attacks

def _safe_ratio(n,d):
    if n is None or d is None or d==0:return None
    return round(n/d,4)

def compute_c_values(attacks):
    vb={i+1:a["attack_volume_v1b"] for i,a in enumerate(attacks)}
    va={i+1:a["attack_volume_v1a"] for i,a in enumerate(attacks)}
    for i,a in enumerate(attacks):
        n=i+1; b1=vb.get(1); a1=va.get(1)
        a["c21"]=_safe_ratio(vb.get(2),b1) if n==2 else None
        a["c31"]=_safe_ratio(vb.get(3),b1) if n>=3 else None
        a["c32"]=_safe_ratio(vb.get(3),vb.get(2)) if n==3 else None
        a["c41"]=_safe_ratio(vb.get(4),b1) if n>=4 else None
        a["c31_v1a"]=_safe_ratio(va.get(3),a1) if n>=3 else None
        a["c41_v1a"]=_safe_ratio(va.get(4),a1) if n>=4 else None
    return attacks

def fill_entry_prices(attacks,df):
    pos={str(row["time"]):i for i,(_,row) in enumerate(df.iterrows())}
    for a in attacks:
        i=pos.get(a["end_time"])
        if i is not None and i+1<len(df):
            b=df.iloc[i+1]; a["entry_next_open"]=float(b["open"] or 0); a["entry_next_close"]=float(b["close"] or 0)
    return attacks
