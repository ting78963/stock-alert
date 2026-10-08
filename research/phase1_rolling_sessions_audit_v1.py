#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared history calendar/rolling-window audit. READ ONLY; no Fugle calls.
Checks F10 session consistency and derives the latest 5 complete sessions
from stored F10 daily volumes, without inventing holiday sessions.
"""
import argparse, sqlite3, json
from pathlib import Path
from collections import Counter

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",type=Path,default=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3"))
    ap.add_argument("--asof",required=True,help="Exclusive YYYY-MM-DD trading snapshot date")
    args=ap.parse_args()
    if not args.db.is_file(): raise SystemExit("STOP: database missing")
    con=sqlite3.connect(args.db.resolve().as_uri()+"?mode=ro",uri=True)
    try:
        rows=con.execute("SELECT symbol,day,full FROM f10_day WHERE day < ? ORDER BY symbol,day DESC",(args.asof,)).fetchall()
        if not rows: raise SystemExit("STOP: no F10 sessions before asof")
        by={}
        for symbol,day,full in rows:
            by.setdefault(str(symbol),[]).append((str(day),float(full)))
        coverage=Counter(len(v) for v in by.values())
        ready={}
        for symbol,history in by.items():
            if len(history)>=5 and all(v>=0 for _,v in history[:5]):
                ready[symbol]={"last_complete_day":history[0][0],"vr5_denominator_zhang":sum(v for _,v in history[:5])/5,"five_days":[d for d,_ in history[:5]]}
        # This is a diagnostic baseline only; per-symbol missing days must be checked
        # against the authoritative trading calendar before any live use.
        latest=Counter(v[0][0] for v in by.values())
        print(json.dumps({"mode":"READ_ONLY_DIAGNOSTIC","asof_exclusive":args.asof,
            "symbols":len(by),"session_count_distribution":dict(sorted(coverage.items())),
            "last_day_distribution":dict(sorted(latest.items())),
            "vr5_denominator_candidates":len(ready),
            "WARNING":"F10 is 11-session minute-volume baseline; NOT full OHLCV history. Do not treat five available rows as five consecutive market sessions without calendar verification. No live A changes."},
            ensure_ascii=False,indent=2))
    finally: con.close()
if __name__=="__main__":main()
