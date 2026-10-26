"""Pure indicator calculations ported from ting78963/stock index.html (main).
No LINE I/O, A/B decisions, or event mutations.
Input: ascending daily OHLC bars with date, close, high/max, low/min.
"""
from datetime import date
from math import isfinite

def _round_js(x, digits=0):
    # JavaScript Math.round (positive half rounds toward +infinity).
    from math import floor
    p=10**digits
    return floor(x*p+0.5)/p

def _ma(values, n, i):
    return sum(values[i-n+1:i+1])/n

def ma_cross_day(bars):
    if len(bars)<25:return None
    c=[float(x["close"]) for x in bars]
    n=len(c)
    for day in range(1,6):
        i=n-day
        if i<20:break
        if _ma(c,5,i-1)<=_ma(c,20,i-1) and _ma(c,5,i)>_ma(c,20,i):
            return day
    return None

def ma_prepare(bars):
    if len(bars)<25:return False
    c=[float(x["close"]) for x in bars];i=len(c)-1
    m5=_ma(c,5,i);m20=_ma(c,20,i)
    return m5<m20 and m20>0 and (m20-m5)/m20*100<=1 and m5>_ma(c,5,i-1)

def weekly_kd(bars):
    if len(bars)<30:return None
    weeks=[];group=[]
    for j,row in enumerate(bars):
        day=date.fromisoformat(str(row["date"])[:10]).weekday()
        if day==0 and group:
            weeks.append(_week(group));group=[]
        group.append(row)
        if j==len(bars)-1:weeks.append(_week(group))
    if len(weeks)<12:return None
    k=d=50.;hist=[]
    for i in range(8,len(weeks)):
        sample=weeks[i-8:i+1]
        hi=max(r["high"] for r in sample);lo=min(r["low"] for r in sample)
        rsv=50 if hi==lo else (weeks[i]["close"]-lo)/(hi-lo)*100
        k=k*2/3+rsv/3;d=d*2/3+k/3
        hist.append((_round_js(k,1),_round_js(d,1)))
    if len(hist)<6:return None
    pk,pd=hist[-2];ck,cd=hist[-1]
    if pk<pd and ck>cd:return "golden_cross"
    if ck<cd and cd-ck<=5 and ck>pk:return "prepare"
    return None

def _week(group):
    return {"close":float(group[-1]["close"]),
            "high":max(float(x.get("max",x.get("high",x["close"]))) for x in group),
            "low":min(float(x.get("min",x.get("low",x["close"]))) for x in group)}

def macd(closes):
    closes=[float(x) for x in closes]
    if len(closes)<35:return {"hist":None,"prev_hist":None,"histArr":[]}
    def ema(n):
        out=[None]*(n-1);e=sum(closes[:n])/n;out.append(e)
        for v in closes[n:]:
            e=v*(2/(n+1))+e*(1-2/(n+1));out.append(e)
        return out
    a=ema(12);b=ema(26)
    dif=[x-y for x,y in zip(a,b) if x is not None and y is not None]
    if len(dif)<9:return {"hist":None,"prev_hist":None,"histArr":[]}
    sig=sum(dif[:9])/9;h=[]
    for i,v in enumerate(dif):
        if i<8:continue
        if i>8:sig=v*.2+sig*.8
        h.append(_round_js(v-sig,2))
    return {"hist":h[-1] if h else None,
            "prev_hist":h[-2] if len(h)>1 else None,
            "histArr":h[-5:]}

def calculate(bars, snapshot_close=None):
    """Compute stock-screen labels. Snapshot only affects displayed OSC, not strong-buy."""
    bars=sorted(bars,key=lambda x:str(x["date"]))
    if not bars:return {}
    day=ma_cross_day(bars);prep=ma_prepare(bars);wk=weekly_kd(bars)
    raw=macd([r["close"] for r in bars])
    display_bars=[r["close"] for r in bars]
    if snapshot_close is not None and isfinite(float(snapshot_close)) and float(snapshot_close)>0:
        display_bars[-1]=float(snapshot_close)
    display=macd(display_bars)
    h=raw["histArr"][-3:]
    strong=wk=="golden_cross" and len(h)>=2 and h[-1]>h[0] and (prep or day==1)
    delta=None
    if display["hist"] is not None and display["prev_hist"] is not None:
        delta=display["hist"]-display["prev_hist"]
    return {"weekly_kd":wk,"ma_cross_day":day,"ma_prepare":prep,
            "osc":display["hist"],"osc_delta":delta,"strong_buy":bool(strong)}
