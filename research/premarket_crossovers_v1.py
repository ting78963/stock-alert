"""Premarket MA crossover classification, with TWD direction inverted."""
def classify(current,previous,short,long,invert=False):
    if not current or not previous:return "unavailable"
    a,b=current.get(short),current.get(long)
    p,q=previous.get(short),previous.get(long)
    if any(v is None for v in (a,b,p,q)):return "unavailable"
    sign=-1 if invert else 1
    now=(a-b)*sign
    before=(p-q)*sign
    if now>0 and before<=0:return "golden_cross"
    if now<0 and before>=0:return "death_cross"
    return "bullish" if now>0 else "bearish" if now<0 else "neutral"

def market_crossovers(indicators):
    ta=indicators.get("taiex") or {}
    fx=indicators.get("usdtwd") or {}
    return {"taiex_daily":classify(ta,ta.get("previous"),"daily_ma20","daily_ma100"),
            "taiex_weekly":classify(ta,ta.get("previous_week"),"weekly_ma20","weekly_ma100"),
            "twd_daily":classify(fx,fx.get("previous"),"daily_ma5","daily_ma20",invert=True)}
