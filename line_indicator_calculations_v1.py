"""Pure, side-effect-free parity port of stock/index.html indicators.

Input rows: chronological dictionaries with date (YYYY-MM-DD), high, low, close.
These functions do NOT query data, mutate state, send LINE, or change A/B rules.
"""
from datetime import date
from math import floor

def js_round(x, digits=0):
    scale=10**digits
    return floor(x*scale+0.5)/scale

def ma_cross_day(rows):
    if len(rows)<25:return None
    c=[float(r["close"]) for r in rows]
    def ma(n,i):return sum(c[i-n+1:i+1])/n
    for day in range(1,6):
        i=len(c)-day
        if i<20:break
        if ma(5,i-1)<=ma(20,i-1) and ma(5,i)>ma(20,i):return day
    return None

def ma_prepare(rows):
    if len(rows)<25:return False
    c=[float(r["close"]) for r in rows]
    def ma(n,i):return sum(c[i-n+1:i+1])/n
    i=len(c)-1
    m5,m20,prev=ma(5,i),ma(20,i),ma(5,i-1)
    return m5<m20 and (m20-m5)/m20*100<=1 and m5>prev

def kd(ohlc, period=9):
    if len(ohlc)<period:return []
    k=d=50.0
    hist=[]
    for i in range(period-1,len(ohlc)):
        segment=ohlc[i-period+1:i+1]
        hi=max(float(r["high"]) for r in segment)
        lo=min(float(r["low"]) for r in segment)
        cl=float(ohlc[i]["close"])
        rsv=50 if hi==lo else (cl-lo)/(hi-lo)*100
        pk,pd=k,d
        k=k*2/3+rsv/3
        d=d*2/3+k/3
        hist.append({"k":js_round(k,1),"d":js_round(d,1),
                     "pk":js_round(pk,1),"pd":js_round(pd,1)})
    return hist

def weekly_kd_label(rows):
    if len(rows)<30:return None
    weeks=[];week=[]
    for i,r in enumerate(rows):
        if date.fromisoformat(r["date"]).weekday()==0 and week:
            weeks.append({"close":float(week[-1]["close"]),
                          "high":max(float(x["high"]) for x in week),
                          "low":min(float(x["low"]) for x in week)})
            week=[]
        week.append(r)
        if i==len(rows)-1:
            weeks.append({"close":float(week[-1]["close"]),
                          "high":max(float(x["high"]) for x in week),
                          "low":min(float(x["low"]) for x in week)})
    if len(weeks)<12:return None
    hist=kd(weeks)
    if len(hist)<6:return None
    cur,prev=hist[-1],hist[-2]
    if prev["k"]<prev["d"] and cur["k"]>cur["d"]:return "golden_cross"
    if cur["k"]<cur["d"] and cur["d"]-cur["k"]<=5 and cur["k"]>prev["k"]:return "prepare"
    return None

def macd(closes,fast=12,slow=26,signal=9):
    empty={"dif":None,"sig":None,"hist":None,"prev_hist":None,"histArr":[],"histArr5":[]}
    if len(closes)<slow+signal:return empty
    c=[float(x["close"] if isinstance(x,dict) else x) for x in closes]
    def ema(arr,n):
        init=sum(arr[:n])/n
        e=init;k=2/(n+1);out=[]
        for i,v in enumerate(arr):
            if i<n-1:out.append(None)
            elif i==n-1:out.append(init)
            else:
                e=v*k+e*(1-k)
                out.append(e)
        return out
    fe,se=ema(c,fast),ema(c,slow)
    dif=[x-y for x,y in zip(fe,se) if x is not None and y is not None]
    if len(dif)<signal:return empty
    sigarr=ema(dif,signal)
    h=[js_round(v-s,2) for v,s in zip(dif,sigarr) if s is not None]
    return {"dif":js_round(dif[-1],2),"sig":js_round(sigarr[-1],2),
            "hist":h[-1],"prev_hist":h[-2] if len(h)>1 else None,
            "histArr":h[-3:],"histArr5":h[-5:]}

def strong_buy(rows):
    """Website uses completed daily rows, NOT projected intraday OSC."""
    if len(rows)<35:return False
    osc=macd([r["close"] for r in rows])["histArr"]
    return (weekly_kd_label(rows)=="golden_cross"
            and len(osc)==3 and osc[-1]>osc[0]
            and (ma_prepare(rows) or ma_cross_day(rows)==1))
