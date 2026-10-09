#!/usr/bin/env python3
"""Incremental F11 metadata backfill. DRY RUN by default; explicit --execute required.
Staging utility only; never starts A/B/LINE. Saves only validated F11 responses.
"""
import argparse,json,os,sqlite3,time,urllib.request,urllib.error
from pathlib import Path
DB=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
CACHE=Path("/var/data/stock-alert/a_f11_metadata_v1.json")
BASE="https://api.fugle.tw/marketdata/v1.0/stock/intraday/ticker/"
def valid(symbol,row):
    return isinstance(row,dict) and str(row.get("symbol") or "")==symbol and all(str(row.get(k) or "") for k in ("market","securityType","industry"))
def atomic_save(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    with tmp.open("w",encoding="utf-8") as out:
        json.dump({"symbols":rows},out,ensure_ascii=False,indent=2)
        out.flush();os.fsync(out.fileno())
    os.replace(tmp,path)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--delay",type=float,default=3.0)
    p.add_argument("--output",type=Path,default=None,help="Required with --execute; isolated staging cache path")
    a=p.parse_args()
    if not 1<=a.limit<=20:raise SystemExit("STOP: limit must be 1..20")
    if a.delay<3:raise SystemExit("STOP: delay must be >=3 seconds")
    if not DB.is_file() or not CACHE.is_file():raise SystemExit("STOP: required input missing")
    db=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
    try:universe={str(r[0]) for r in db.execute("SELECT DISTINCT symbol FROM daily_ohlcv")}
    finally:db.close()
    raw=json.loads(CACHE.read_text(encoding="utf-8"))
    rows=raw.get("symbols",raw)
    if not isinstance(rows,dict):raise SystemExit("STOP: cache invalid")
    missing=sorted(universe-{s for s,v in rows.items() if valid(s,v)})
    batch=missing[:a.limit]
    print("UNIVERSE =",len(universe),"VALID_CACHE =",len(universe)-len(missing),"MISSING =",len(missing))
    print("SELECTED =",",".join(batch))
    if not a.execute:
        print("DRY_RUN_ONLY=YES; HTTP=NONE; WRITES=NONE");return
    if a.output is None:raise SystemExit("STOP: --execute requires explicit --output under /tmp or /var/data/stock-alert/f11-staging/")
    target=a.output.resolve()
    staging=Path("/var/data/stock-alert/f11-staging").resolve()
    if not (target.is_relative_to(Path("/tmp").resolve()) or target.is_relative_to(staging)):
        raise SystemExit("STOP: output must be in /tmp or dedicated f11-staging directory")
    if target==CACHE.resolve():raise SystemExit("STOP: production F11 cache forbidden")
    if target.exists():
        prior=json.loads(target.read_text(encoding="utf-8"))
        existing=prior.get("symbols",prior)
        if not isinstance(existing,dict):raise SystemExit("STOP: staging cache invalid")
        for symbol,record in existing.items():
            if valid(symbol,record):rows[symbol]=record
        missing=sorted(universe-{s for s,v in rows.items() if valid(s,v)})
        batch=missing[:a.limit]
        print("STAGING_REUSE =",len(existing),"STILL_MISSING =",len(missing))
    key=os.environ.get("FUGLE_API_KEY") or os.environ.get("FUGLE_KEY")
    if not key:raise SystemExit("STOP: FUGLE_API_KEY/FUGLE_KEY absent")
    print("EXECUTE REQUESTED; OUTPUT =",str(target),"MAX_CALLS =",len(batch),"MIN_DELAY_SEC =",a.delay)
    done=0
    for idx,symbol in enumerate(batch):
        if idx:time.sleep(a.delay)
        request=urllib.request.Request(BASE+symbol,headers={"X-API-KEY":key,"Accept":"application/json"})
        try:
            with urllib.request.urlopen(request,timeout=15) as resp:
                payload=json.load(resp)
        except urllib.error.HTTPError as exc:
            print("HTTP_ERROR",symbol,exc.code)
            if exc.code==429:
                print("STOP: 429 rate limit; do not retry immediately");break
            continue
        except Exception as exc:
            print("FETCH_ERROR",symbol,type(exc).__name__);continue
        if not valid(symbol,payload):
            print("INVALID_IDENTITY_OR_FIELDS",symbol);continue
        rows[symbol]=payload
        atomic_save(target,rows)
        done+=1
        print("SAVED",symbol)
    print("SAVED_TOTAL =",done,"REMAINING_ESTIMATE =",len(missing)-done)
    print("A/B/LINE=NONE; PRODUCTION_CODE_UNCHANGED=YES")
if __name__=="__main__":main()
