"""Compare exposure caps using daily closes, no network or production writes.
Signals at close execute at next session close; no same-close lookahead.
Index proxy, cash earns zero, costs charged on traded notional.
"""
from datetime import date
from math import isfinite
from research.premarket_risk_waterline_v1 import snapshot

def compare(rows, cost=0.001, caps=(90,80,70)):
    if not 0 <= cost < 1:
        raise ValueError("invalid cost")
    days = [(date.fromisoformat(r["date"]),float(r["close"])) for r in rows]
    days.sort()
    if len({d for d,p in days}) != len(days) or any(not isfinite(p) or p<=0 for d,p in days):
        raise ValueError("invalid daily history")
    weeks = {}
    closes = []
    signals = []
    for d,p in days:
        key = tuple(d.isocalendar()[:2])
        completed = [v for k,v in weeks.items() if k < key]
        closes.append(p)
        s = snapshot(closes,sum(completed[-20:])/20) if len(completed)>=20 else None
        signals.append((d,p,s["target"] if s else None))
        weeks[key] = p
    start = next((i for i,(_,_,s) in enumerate(signals) if s is not None),None)
    if start is None or start+1>=len(signals):
        raise ValueError("insufficient history")
    results = []
    for cap in caps:
        equity=peak=1.0
        stock=0.0
        cash=1.0
        last_target=None
        changes=0
        turnover=drawdown=0.0
        for i in range(start+1,len(signals)):
            d,p,_=signals[i]
            stock *= p/signals[i-1][1]
            equity=stock+cash
            signal=signals[i-1][2]
            if signal is not None:
                target=min(signal,cap)
                if target!=last_target:
                    weight=target/100
                    # Solve for desired weight after proportional transaction cost.
                    diff=weight*equity-stock
                    trade=diff/(1+weight*cost) if diff>=0 else diff/(1-weight*cost)
                    fee=abs(trade)*cost
                    turnover+=abs(trade)/equity
                    stock+=trade
                    cash-=trade+fee
                    changes+=int(last_target is not None)
                    last_target=target
            equity=stock+cash
            peak=max(peak,equity)
            drawdown=max(drawdown,1-equity/peak)
        results.append({"cap":cap,"return_pct":100*(equity-1),
                        "max_drawdown_pct":100*drawdown,"changes":changes,
                        "turnover_pct":100*turnover})
    return {"first_execution":signals[start+1][0].isoformat(),
            "end":signals[-1][0].isoformat(),"cost_per_side":cost,"results":results}

if __name__=="__main__":
    import argparse,json
    parser=argparse.ArgumentParser()
    parser.add_argument("history")
    parser.add_argument("--cost",type=float,default=0.001)
    args=parser.parse_args()
    with open(args.history,encoding="utf-8") as f:
        obj=json.load(f)
    print(json.dumps(compare(obj["rows"],args.cost),ensure_ascii=False,indent=2))
