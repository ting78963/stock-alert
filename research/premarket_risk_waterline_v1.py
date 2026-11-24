"""Research-only exposure matrix; analyst-inspired, not their proprietary rules."""
from math import isfinite

MATRIX = {90: (90,70,50), 70: (70,50,30),
          50: (50,30,20), 30: (30,20,20)}

def target_for(base, above5, above10):
    if base not in MATRIX or type(above5) is not bool or type(above10) is not bool:
        raise ValueError("invalid baseline or short-term state")
    return MATRIX[base][2-int(above5)-int(above10)]

def snapshot(closes, base):
    if len(closes)<10 or any(not isfinite(x) or x<=0 for x in closes[-10:]):
        return None
    price=closes[-1]
    ma={n:sum(closes[-n:])/n for n in (5,10)}
    if price in ma.values():
        return None  # equality: defer rather than invent a crossing
    above={n:price>v for n,v in ma.items()}
    return {"base":base,"target":target_for(base,above[5],above[10]),
            "above":above,"ma":ma,
            "bias":{n:(price/v-1)*100 for n,v in ma.items()}}

def analyze(closes, base, previous_base, previous_target=None):
    current=snapshot(closes,base)
    previous=snapshot(closes[:-1],previous_base)
    if current is None or previous is None:
        return {"status":"pending","target":previous_target,"action":"待確認"}
    events={n:"突破" if current["above"][n] else "跌破"
            for n in current["above"] if current["above"][n]!=previous["above"][n]}
    prior=previous["target"] if previous_target is None else previous_target
    if prior not in (20,30,50,70,90):
        raise ValueError("invalid previous target")
    delta=current["target"]-prior
    return {**current,"status":"ok","previous_target":prior,
            "delta":delta,"events":events,"baseline_changed":base!=previous_base,
            "action":"評估增碼" if delta>0 else "評估減碼、回收現金" if delta<0 else "維持"}
