"""Research-only exposure model. Not a reproduction of either analyst's rules."""
from math import isfinite

def snapshot(closes):
    if len(closes)<101 or any(not isfinite(x) or x<=0 for x in closes[-101:]):
        return None
    price=closes[-1]
    ma={n:sum(closes[-n:])/n for n in (5,10,20,100)}
    above={n:price>v for n,v in ma.items()}
    if price in ma.values():
        return None  # boundary: do not issue a new target
    a,b,c,d=(above[n] for n in (5,10,20,100))
    lamp="red" if c and d else "green" if not c and not d else "yellow"
    target=(90 if a and b else 70) if lamp=="red" else (50 if c else 30) if lamp=="yellow" else (30 if a or b else 10)
    return {"lamp":lamp,"target":target,"above":above,"ma":ma,
            "bias":{n:(price/v-1)*100 for n,v in ma.items()}}

def analyze(closes):
    current=snapshot(closes)
    previous=snapshot(closes[:-1])
    if current is None or previous is None:
        return {"status":"insufficient","target":None,"action":"待確認"}
    events={n:"突破" if current["above"][n] else "跌破"
            for n in current["above"] if current["above"][n]!=previous["above"][n]}
    delta=current["target"]-previous["target"]
    return {**current,"status":"ok","previous_raw_target":previous["target"],
            "delta":delta,"events":events,
            "action":"評估增碼" if delta>0 else "評估減碼、回收現金" if delta<0 else "維持"}
