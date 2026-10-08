#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent, resumable Fugle daily OHLCV history builder.
STAGING ONLY: never changes production A/B/LINE or existing F10 DB.
Fugle historical D volume is shares; stored volume_zhang = shares / 1000.
A day is complete only when it precedes --asof (exclusive, Taiwan local date).
"""
import argparse, datetime as dt, json, os, sqlite3, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

F10=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
OUT=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
BASE="https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/"

def dbopen(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS daily_ohlcv(
      symbol TEXT NOT NULL,day TEXT NOT NULL,
      open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,
      close REAL NOT NULL,volume_zhang REAL NOT NULL,
      PRIMARY KEY(symbol,day));
    CREATE TABLE IF NOT EXISTS fetch_status(
      symbol TEXT PRIMARY KEY,covered_through TEXT NOT NULL,
      last_success_utc TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS fetch_error(
      symbol TEXT PRIMARY KEY, error TEXT NOT NULL,last_error_utc TEXT NOT NULL);
    """)
    return db

def fetch(symbol,start,end,key,timeout):
    q=urllib.parse.urlencode({"from":start,"to":end,"timeframe":"D","fields":"open,high,low,close,volume","sort":"asc"})
    req=urllib.request.Request(BASE+urllib.parse.quote(symbol)+"?"+q,
        headers={"X-API-KEY":key,"User-Agent":"shared-history-stage-v1"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.load(r)

def parse(symbol,reply,start,end):
    if str(reply.get("symbol"))!=symbol: raise ValueError("symbol identity mismatch")
    data=reply.get("data")
    if not isinstance(data,list): raise ValueError("missing data array")
    out={}
    for item in data:
        day=str(item.get("date",""))[:10]
        dt.date.fromisoformat(day)
        if not(start<=day<=end):raise ValueError("response outside requested range")
        op,hi,lo,cl=(float(item[k]) for k in ("open","high","low","close"))
        vol=float(item["volume"])/1000
        if min(op,hi,lo,cl)<=0 or vol<0 or hi<max(op,cl,lo) or lo>min(op,cl,hi):
            raise ValueError("invalid OHLCV")
        row=(symbol,day,op,hi,lo,cl,vol)
        if day in out and out[day]!=row:raise ValueError("conflicting duplicate date")
        out[day]=row
    return list(out.values())

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--asof",required=True,help="Exclusive YYYY-MM-DD, usually next market date")
    p.add_argument("--history-calendar-days",type=int,default=200)
    p.add_argument("--delay",type=float,default=5)
    p.add_argument("--max-retries",type=int,default=5)
    p.add_argument("--timeout",type=float,default=20)
    p.add_argument("--db",type=Path,default=OUT)
    p.add_argument("--f10",type=Path,default=F10)
    p.add_argument("--limit",type=int,default=0,help="0=all; use 2 for smoke test")
    p.add_argument("--dry-run",action="store_true",help="Print planned requests; no network and no database writes")
    a=p.parse_args()
    if a.delay<1 or a.history_calendar_days<170 or a.max_retries<0:
        raise SystemExit("STOP: invalid parameters")
    asof=dt.date.fromisoformat(a.asof)
    end=asof-dt.timedelta(days=1)
    start=end-dt.timedelta(days=a.history_calendar_days)
    if asof>dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()+dt.timedelta(days=1):
        raise SystemExit("STOP: asof too far in future")
    if not a.f10.is_file():raise SystemExit("STOP: F10 source missing")
    if a.db.resolve()==a.f10.resolve():raise SystemExit("STOP: staging DB must differ from F10")
    key=os.environ.get("FUGLE_API_KEY","").strip()
    if not key and not a.dry_run:raise SystemExit("STOP: FUGLE_API_KEY missing")
    src=sqlite3.connect(a.f10.resolve().as_uri()+"?mode=ro",uri=True)
    try: symbols=[str(x[0]) for x in src.execute("SELECT symbol FROM member ORDER BY symbol")]
    finally:src.close()
    if not symbols or len(set(symbols))!=len(symbols):raise SystemExit("STOP: invalid member universe")
    if a.dry_run:
        print(json.dumps({"mode":"DRY_RUN","universe":len(symbols),"selected":symbols[:a.limit or None],"from":start.isoformat(),"to":end.isoformat(),"delay_seconds":a.delay,"output":str(a.db),"warning":"No network; no DB writes; date completeness not yet certified"},ensure_ascii=False))
        return
    db=dbopen(a.db)
    try:
        total=len(symbols); done=0; failed=0; skipped=0
        for index,sym in enumerate(symbols[:a.limit or None],1):
            existing=db.execute("SELECT covered_through FROM fetch_status WHERE symbol=?",(sym,)).fetchone()
            if existing and existing[0]>=end.isoformat():
                skipped+=1;continue
            fetch_start=max(start,dt.date.fromisoformat(existing[0])+dt.timedelta(days=1)) if existing else start
            if fetch_start>end:skipped+=1;continue
            error=None
            for attempt in range(a.max_retries+1):
                try:
                    reply=fetch(sym,fetch_start.isoformat(),end.isoformat(),key,a.timeout)
                    rows=parse(sym,reply,fetch_start.isoformat(),end.isoformat())
                    with db:
                        for row in rows:
                            old=db.execute("SELECT open,high,low,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day=?",row[:2]).fetchone()
                            if old is not None and any(abs(float(x)-float(y))>1e-6 for x,y in zip(old,row[2:])):
                                raise ValueError("existing OHLCV conflict "+str(row[:2]))
                            db.execute("INSERT OR IGNORE INTO daily_ohlcv VALUES(?,?,?,?,?,?,?)",row)
                        db.execute("INSERT INTO fetch_status VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET covered_through=excluded.covered_through,last_success_utc=excluded.last_success_utc",
                            (sym,end.isoformat(),dt.datetime.now(dt.timezone.utc).isoformat()))
                        db.execute("DELETE FROM fetch_error WHERE symbol=?",(sym,))
                    done+=1;error=None;break
                except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,KeyError) as ex:
                    error=f"{type(ex).__name__}: {getattr(ex,'code','')} {ex}"
                    if isinstance(ex,ValueError) or isinstance(ex,KeyError):break
                    if attempt<a.max_retries:
                        wait=max(a.delay,60*(2**min(attempt,3))) if isinstance(ex,urllib.error.HTTPError) and ex.code==429 else a.delay*(attempt+1)
                        print(f"[RETRY] {sym} attempt={attempt+1} wait={wait:.0f}s {type(ex).__name__}",flush=True)
                        time.sleep(wait)
                finally:
                    time.sleep(a.delay)
            if error:
                failed+=1
                with db:db.execute("INSERT INTO fetch_error VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET error=excluded.error,last_error_utc=excluded.last_error_utc",
                    (sym,error[:400],dt.datetime.now(dt.timezone.utc).isoformat()))
                print(f"[FAIL] {index}/{total} {sym} {error}",flush=True)
            elif index%25==0:print(f"[PROGRESS] {index}/{total} done={done} skipped={skipped} failed={failed}",flush=True)
        print(json.dumps({"status":"COMPLETE" if failed==0 else "INCOMPLETE","universe":total,"processed":done,"skipped":skipped,"failed":failed,"database":str(a.db),"request_checked_through":end.isoformat(),"note":"Successful query coverage only, not proof of per-day trades or calendar completeness. Staging only; A/B/LINE unchanged"},ensure_ascii=False))
        if failed:raise SystemExit(2)
    finally:db.close()

if __name__=="__main__":main()
