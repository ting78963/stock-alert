"""Deterministic research-only exposure rules; completed daily closes only."""
from math import isfinite, fsum

PERIODS = (5, 10, 20, 100)

def target_for(above5, above10, above20, above100, above_week20):
    states = (above5, above10, above20, above100, above_week20)
    if any(type(x) is not bool for x in states):
        raise ValueError("boolean MA states required")
    raw = max(20, 10 + 20 * sum((above10, above10, above20, above100)))
    capped = min(raw, 80, 90 if above20 else 50,
                 90 if above100 else 30, 90 if above_week20 else 30)
    # Apply the short-term defensive step after caps, so a cap cannot mask it.
    levels = (20, 30, 50, 70, 80)
    return capped if above5 and above10 else levels[max(0, levels.index(capped)-1)]

def snapshot(closes, week20, prior_above=None):
    if len(closes) < 100 or week20 is None:
        return None
    if not isfinite(week20) or week20 <= 0 or any(
            not isfinite(x) or x <= 0 for x in closes[-100:]):
        return None
    price = closes[-1]
    ma = {n: sum(closes[-n:])/n for n in PERIODS}
    ma["week20"] = week20
    touching = {n for n,v in ma.items() if price == v}
    # At a touch retain the prior side; without a known side use the conservative side.
    above = {n: (prior_above or {}).get(n, False) if n in touching else price > v
             for n,v in ma.items()}
    raw = max(20, 10 + 20 * sum((above[10], above[10], above[20], above[100])))
    target = target_for(*(above[n] for n in (*PERIODS,"week20")))
    return {"target":target,"raw_target":raw,"above":above,"ma":ma,
            "cash":100-target,"touching":sorted(touching,key=str),
            "caps":{n:cap for n,cap in ((20,50),(100,30),("week20",30))
                    if not above[n]},
            "bias":{n:(price/v-1)*100 for n,v in ma.items()}}

def analyze(closes, week20, previous_week20, previous_target=None, previous_above=None):
    # Caller supplies each day's own completed-week MA, without lookahead.
    previous = snapshot(closes[:-1], previous_week20, previous_above)
    current = snapshot(closes, week20, previous['above'] if previous else None)
    if previous_target is not None and previous_target not in (20,30,50,70,80):
        raise ValueError("invalid previous target")
    if current is None or previous is None:
        return {"status":"pending","target":previous_target,"action":"待確認"}
    prior = previous["target"] if previous_target is None else previous_target
    events = {n:"突破" if current["above"][n] else "跌破"
              for n in current["above"] if n not in current["touching"] and (n not in previous["touching"] or n in (previous_above or {}))
              and current["above"][n]!=previous["above"][n]}
    delta = current["target"] - prior
    return {**current,"status":"ok","previous_target":prior,"delta":delta,
            "events":events,"action":"評估增碼" if delta>0 else
            "評估減碼、回收現金" if delta<0 else "維持"}


def seasonal_bias(closes):
    if len(closes)<60 or any(not isfinite(x) or x<=0 for x in closes[-60:]):
        return {"status":"pending"}
    ma=fsum(closes[-60:])/60
    price=closes[-1]
    bias=(price/ma-1)*100
    # Remove numerical noise only, not economically meaningful differences.
    boundary=round(bias, 10)
    if boundary>=14:
        level="extreme"
    elif boundary>=10:
        level="high"
    elif boundary>=8:
        level="early"
    elif boundary< -10:
        level="negative"
    else:
        level="normal"
    return {"status":"ok","ma60":ma,"bias":bias,"level":level}


def analyze_history(rows, as_of):
    """Use the same completed-week convention as the existing market report."""
    from datetime import date, timedelta
    from taiex_market_history_v1 import normalize_daily, completed_week_closes
    daily = [r for r in normalize_daily(rows) if r["date"] < str(as_of)[:10]]
    seasonal = seasonal_bias([r["close"] for r in daily])
    if len(daily) < 101:
        return {"status":"pending","target":None,"action":"待確認","seasonal_bias":seasonal}
    def week_ma(history, cutoff):
        values = [r["close"] for r in completed_week_closes(history, cutoff)]
        return sum(values[-20:])/20 if len(values)>=20 else None
    previous_cutoff = date.fromisoformat(daily[-2]["date"]) + timedelta(days=1)
    closes = [r["close"] for r in daily]
    prior_above = {}
    unresolved = set((*PERIODS, "week20"))
    for i in range(len(daily)-3, 98, -1):
        cutoff = date.fromisoformat(daily[i]["date"]) + timedelta(days=1)
        state = snapshot(closes[:i+1], week_ma(daily[:i+1], cutoff))
        if state is None:
            break
        for n in unresolved - set(state["touching"]):
            prior_above[n] = state["above"][n]
        unresolved -= prior_above.keys()
        if not unresolved:
            break
    result = analyze(closes,
                     week_ma(daily, as_of),
                     week_ma(daily[:-1], previous_cutoff), previous_above=prior_above)
    return {**result,"close_date":daily[-1]["date"],"seasonal_bias":seasonal}
