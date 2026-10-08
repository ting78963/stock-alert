#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 staging: import existing F10 and A daily cache into a separate SQLite DB.
NO NETWORK. NO PRODUCTION WRITES. Does not alter A/B/LINE.
This is an evidence-gathering migration prototype, NOT a live A data adapter.
"""
import argparse
import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

DEFAULT_F10 = Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
DEFAULT_A = Path("/var/data/stock-alert/a_cache_backup_20261001/a_history_cache_v2_4.json")

def open_ro(path):
    if not path.is_file():
        raise RuntimeError(f"source missing: {path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)

def valid_day(s):
    try:
        return date.fromisoformat(str(s)[:10]).isoformat()
    except (TypeError, ValueError):
        raise RuntimeError(f"invalid day: {s!r}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--f10",type=Path,default=DEFAULT_F10)
    p.add_argument("--a-cache",type=Path,default=DEFAULT_A)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--asof",required=True,help="YYYY-MM-DD; never import dates >= this day")
    a=p.parse_args()
    asof=valid_day(a.asof)
    if a.output.exists():
        raise SystemExit(f"STOP: output already exists: {a.output}")
    if not a.output.parent.is_dir():
        raise SystemExit("STOP: output parent directory missing; use /tmp")
    if a.output.resolve() in (a.f10.resolve(),a.a_cache.resolve()):
        raise SystemExit("STOP: output equals a source")
    src=open_ro(a.f10)
    if not a.a_cache.is_file():
        raise SystemExit(f"STOP: A cache missing: {a.a_cache}")
    obj=json.loads(a.a_cache.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):
        raise SystemExit("STOP: A cache is not a JSON object")
    # First validate all identities, then write to a fresh staging file.
    f10_rows=src.execute("SELECT symbol,day,full,pts_json FROM f10_day ORDER BY symbol,day").fetchall()
    counts=Counter()
    checked=[]
    for sym,day,full,raw in f10_rows:
        sym=str(sym)
        day=valid_day(day)
        if not sym.isdigit() or len(sym)!=4 or day>=asof or float(full)<=0:
            raise SystemExit(f"STOP: F10 identity/date/volume: {sym} {day}")
        pts=json.loads(raw)
        if not isinstance(pts,list) or not pts:
            raise SystemExit(f"STOP: F10 empty minute curve {sym} {day}")
        if abs(float(pts[-1][1])-float(full))>0.001:
            raise SystemExit(f"STOP: F10 volume integrity {sym} {day}")
        counts[sym]+=1
        checked.append((sym,day,float(full),raw))
    if not checked:
        raise SystemExit("STOP: F10 has no records")
    daily=[]
    covered=[]
    for k,v in obj.items():
        if k.startswith("daily_static_covered|"):
            sym=k.split("|",1)[1]
            if not sym.isdigit() or len(sym)!=4:
                raise SystemExit(f"STOP: bad covered identity {k}")
            ds=valid_day(v)
            if ds>=asof:
                # The cache may contain later days than the requested as-of;
                # do not claim those dates are valid for this snapshot.
                continue
            covered.append((sym,ds))
        elif k.startswith("daily|") or k.startswith("daily_static|"):
            sym=k.split("|",1)[1]
            if not sym.isdigit() or len(sym)!=4 or not isinstance(v,list):
                raise SystemExit(f"STOP: bad daily identity {k}")
            for x in v:
                ds=valid_day(x["date"])
                if ds>=asof:
                    continue
                close=float(x["close"])
                volume=float(x["volume_zhang"])
                if close<=0 or volume<0:
                    raise SystemExit(f"STOP: invalid daily values {sym} {ds}")
                daily.append((sym,ds,close,volume))
    # Historical cache uses daily|symbol|target_day and estvr5|symbol|target_day.\n    # The target day is NOT necessarily the date of each historical bar.\n    dst=sqlite3.connect(a.output)
    try:
        dst.executescript("""
        CREATE TABLE f10_minute_baseline(symbol TEXT NOT NULL, day TEXT NOT NULL, full_volume_zhang REAL NOT NULL, pts_json TEXT NOT NULL, PRIMARY KEY(symbol,day));
        CREATE TABLE daily_history(symbol TEXT NOT NULL, day TEXT NOT NULL, close REAL NOT NULL, volume_zhang REAL NOT NULL, PRIMARY KEY(symbol,day));
        CREATE TABLE daily_coverage(symbol TEXT PRIMARY KEY, covered_through TEXT NOT NULL);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        dst.executemany("INSERT INTO f10_minute_baseline VALUES(?,?,?,?)",checked)
        dst.executemany("INSERT OR IGNORE INTO daily_history VALUES(?,?,?,?)",daily)
        dst.executemany("INSERT INTO daily_coverage VALUES(?,?)",covered)
        dst.executemany("INSERT INTO metadata VALUES(?,?)",[
            ("asof_exclusive",asof),("source_f10",str(a.f10)),
            ("source_a_cache",str(a.a_cache)),("status","STAGING_ONLY_NO_LIVE_READER")])
        dst.commit()
        integrity=dst.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity!="ok":
            raise RuntimeError("SQLite integrity check failed: "+integrity)
        print(json.dumps({
            "status":"PASS_STAGING_ONLY","asof_exclusive":asof,
            "f10_symbols":len(counts),"f10_days":len(checked),
            "f10_symbols_ge10":sum(v>=10 for v in counts.values()),
            "daily_symbols":len({r[0] for r in daily}),
            "daily_rows":len(daily),"daily_unique_rows":dst.execute("SELECT COUNT(*) FROM daily_history").fetchone()[0],"daily_coverage_symbols":len(covered),
            "sqlite_integrity":integrity,"output":str(a.output),
            "important":"No VR5/EVG/VCP values computed yet; live A unchanged."
        },ensure_ascii=False,indent=2))
    finally:
        dst.close()
        src.close()

if __name__=="__main__":
    main()
