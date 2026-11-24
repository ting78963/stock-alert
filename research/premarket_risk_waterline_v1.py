"""Deterministic research-only exposure rules; completed daily closes only."""
from math import isfinite

PERIODS = (5, 10, 20, 100)

def target_for(above5, above10, above20, above100, above_week20):
    states = (above5, above10, above20, above100, above_week20)
    if any(type(x) is not bool for x in states):
        raise ValueError("boolean MA states required")
    raw = max(20, 10 + 20 * sum(states[:4]))
    return min(raw, 90 if above20 else 50,
               90 if above100 else 30, 90 if above_week20 else 30)

def snapshot(closes, week20):
    if len(closes) < 100 or week20 is None:
        return None
    if not isfinite(week20) or week20 <= 0 or any(
            not isfinite(x) or x <= 0 for x in closes[-100:]):
        return None
    price = closes[-1]
    ma = {n: sum(closes[-n:])/n for n in PERIODS}
    ma["week20"] = week20
    # Equality is not a confirmed crossing; defer the recommendation.
    if price in ma.values():
        return None
    above = {n: price > v for n,v in ma.items()}
    raw = max(20, 10 + 20 * sum(above[n] for n in PERIODS))
    target = target_for(*(above[n] for n in (*PERIODS,"week20")))
    return {"target":target,"raw_target":raw,"above":above,"ma":ma,
            "cash":100-target,
            "caps":{n:cap for n,cap in ((20,50),(100,30),("week20",30))
                    if not above[n]},
            "bias":{n:(price/v-1)*100 for n,v in ma.items()}}

def analyze(closes, week20, previous_week20, previous_target=None):
    # Caller supplies each day's own completed-week MA, without lookahead.
    current = snapshot(closes, week20)
    previous = snapshot(closes[:-1], previous_week20)
    if previous_target is not None and previous_target not in (20,30,50,70,90):
        raise ValueError("invalid previous target")
    if current is None or previous is None:
        return {"status":"pending","target":previous_target,"action":"待確認"}
    prior = previous["target"] if previous_target is None else previous_target
    events = {n:"突破" if current["above"][n] else "跌破"
              for n in current["above"] if current["above"][n]!=previous["above"][n]}
    delta = current["target"] - prior
    return {**current,"status":"ok","previous_target":prior,"delta":delta,
            "events":events,"action":"評估增碼" if delta>0 else
            "評估減碼、回收現金" if delta<0 else "維持"}
