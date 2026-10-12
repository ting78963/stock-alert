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
    CREATE TABLE IF NOT EXISTS suspension_meta(
      key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS suspension_watch(
      symbol TEXT PRIMARY KEY, confirmed_source TEXT NOT NULL,
      confirmed_at_utc TEXT NOT NULL, last_probe_day TEXT NOT NULL DEFAULT '',
      last_probe_result TEXT NOT NULL DEFAULT '');
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

def twse_suspension_status(symbol, day, timeout=12):
    """Confirm a TWSE trading halt only from the published effective date range.

    TWTAWU uses Code, TradingHaltDate and TradingResumptionDate; dates are
    compact ROC YYYMMDD. Missing/malformed data is UNKNOWN, never confirmed.
    """
    url="https://openapi.twse.com.tw/v1/exchangeReport/TWTAWU"
    req=urllib.request.Request(url,headers={"User-Agent":"stock-alert-suspension-watch/1"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            data=json.load(response)
    except (urllib.error.URLError,TimeoutError,ValueError):
        return None
    if not isinstance(data,list):
        return None
    def roc_date(value):
        value=str(value).strip()
        if not value:return None
        if len(value)!=7 or not value.isascii() or not value.isdigit():
            raise ValueError("invalid ROC YYYMMDD date")
        return dt.date(int(value[:3])+1911,int(value[3:5]),int(value[5:7]))
    for item in data:
        if not isinstance(item,dict) or "Code" not in item:
            return None
        if str(item["Code"]).strip()!=symbol:
            continue
        if "TradingHaltDate" not in item or "TradingResumptionDate" not in item:
            return None
        try:
            began=roc_date(item["TradingHaltDate"])
            resumed=roc_date(item["TradingResumptionDate"])
        except ValueError:
            return None
        if began and began<=day and (resumed is None or day<resumed):
            return "twse-twtawu"
    return None

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
    p.add_argument("--confirmed-suspended",default="",help="Comma-separated manually verified suspended symbols; no auto-classification from 404")
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
        confirmed={x.strip() for x in a.confirmed_suspended.split(",") if x.strip()}
        if confirmed and not confirmed.issubset(set(symbols)):
            raise SystemExit("STOP: confirmed suspended identity outside member universe")
        # Seed only once: a resumed symbol must never be re-added on the next run.
        if not db.execute("SELECT 1 FROM suspension_meta WHERE key='initial_seed_v1'").fetchone():
            with db:
                for sym in sorted(confirmed):
                    db.execute("INSERT OR IGNORE INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc) VALUES(?,?,?)",
                               (sym,"operator-confirmed",dt.datetime.now(dt.timezone.utc).isoformat()))
                db.execute("INSERT INTO suspension_meta(key,value) VALUES('initial_seed_v1',?)",
                           (dt.datetime.now(dt.timezone.utc).isoformat(),))
        total=len(symbols); done=0; failed=0; skipped=0
        for index,sym in enumerate(symbols[:a.limit or None],1):
            existing=db.execute("SELECT covered_through FROM fetch_status WHERE symbol=?",(sym,)).fetchone()
            watched=db.execute("SELECT last_probe_day FROM suspension_watch WHERE symbol=?",(sym,)).fetchone()
            if existing and existing[0]>=end.isoformat() and not watched:
                skipped+=1;continue
            fetch_start=max(start,dt.date.fromisoformat(existing[0])+dt.timedelta(days=1)) if existing else start
            if fetch_start>end and not watched:skipped+=1;continue
            if fetch_start>end:fetch_start=end
            if watched and watched[0]==end.isoformat():
                skipped+=1;continue
            error=None
            for attempt in range(a.max_retries+1):
                try:
                    reply=fetch(sym,fetch_start.isoformat(),end.isoformat(),key,a.timeout)
                    rows=parse(sym,reply,fetch_start.isoformat(),end.isoformat())
                    # A successful HTTP response without a new valid candle is not a resumption.
                    resumed=bool(watched and any(r[1]==end.isoformat() and r[6]>0 for r in rows))
                    if watched and not resumed:
                        # Preserve valid older bars returned during the daily probe.
                        with db:
                            for row in rows:
                                old=db.execute("SELECT open,high,low,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day=?",row[:2]).fetchone()
                                if old is not None and any(abs(float(x)-float(y))>1e-6 for x,y in zip(old,row[2:])):
                                    raise ValueError("existing OHLCV conflict "+str(row[:2]))
                                db.execute("INSERT OR IGNORE INTO daily_ohlcv VALUES(?,?,?,?,?,?,?)",row)
                            db.execute("UPDATE suspension_watch SET last_probe_day=?,last_probe_result=? WHERE symbol=?",
                                       (end.isoformat(),"no_new_candle",sym))
                        done+=1;error=None;break
                    with db:
                        for row in rows:
                            old=db.execute("SELECT open,high,low,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day=?",row[:2]).fetchone()
                            if old is not None and any(abs(float(x)-float(y))>1e-6 for x,y in zip(old,row[2:])):
                                raise ValueError("existing OHLCV conflict "+str(row[:2]))
                            db.execute("INSERT OR IGNORE INTO daily_ohlcv VALUES(?,?,?,?,?,?,?)",row)
                        db.execute("INSERT INTO fetch_status VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET covered_through=excluded.covered_through,last_success_utc=excluded.last_success_utc",
                            (sym,end.isoformat(),dt.datetime.now(dt.timezone.utc).isoformat()))
                        db.execute("DELETE FROM fetch_error WHERE symbol=?",(sym,))
                        if resumed: db.execute("DELETE FROM suspension_watch WHERE symbol=?",(sym,))
                    done+=1;error=None;break
                except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,KeyError) as ex:
                    error=f"{type(ex).__name__}: {getattr(ex,'code','')} {ex}"
                    if isinstance(ex,(ValueError,KeyError)) or (isinstance(ex,urllib.error.HTTPError) and ex.code==404):break
                    if attempt<a.max_retries:
                        wait=max(a.delay,60*(2**min(attempt,3))) if isinstance(ex,urllib.error.HTTPError) and ex.code==429 else a.delay*(attempt+1)
                        print(f"[RETRY] {sym} attempt={attempt+1} wait={wait:.0f}s {type(ex).__name__}",flush=True)
                        time.sleep(wait)
                finally:
                    time.sleep(a.delay)
            if error and not watched and error.startswith("HTTPError: 404 "):
                source=twse_suspension_status(sym,end,a.timeout)
                if source:
                    with db:
                        db.execute("INSERT OR IGNORE INTO suspension_watch(symbol,confirmed_source,confirmed_at_utc,last_probe_day,last_probe_result) VALUES(?,?,?,?,?)",
                                   (sym,source,dt.datetime.now(dt.timezone.utc).isoformat(),end.isoformat(),"http404"))
                        db.execute("DELETE FROM fetch_error WHERE symbol=?",(sym,))
                    print(f"[SUSPENSION WATCH] {sym} official TWSE confirmation; daily watch activated",flush=True)
                    watched=(end.isoformat(),)
                    error=None
                    done+=1
            if error and watched and error.startswith("HTTPError: 404 "):
                with db:
                    db.execute("UPDATE suspension_watch SET last_probe_day=?,last_probe_result=? WHERE symbol=?",
                               (end.isoformat(),"http404",sym))
                print(f"[SUSPENSION WATCH] {sym} daily probe HTTP 404; remains watched",flush=True)
                error=None
                done+=1
            if error:
                failed+=1
                with db:db.execute("INSERT INTO fetch_error VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET error=excluded.error,last_error_utc=excluded.last_error_utc",
                    (sym,error[:400],dt.datetime.now(dt.timezone.utc).isoformat()))
                print(f"[FAIL] {index}/{total} {sym} {error}",flush=True)
            elif index%25==0:print(f"[PROGRESS] {index}/{total} done={done} skipped={skipped} failed={failed}",flush=True)
        watch_pending=db.execute("SELECT COUNT(*) FROM suspension_watch").fetchone()[0]
        print(json.dumps({"status":"INCOMPLETE" if failed else ("WATCH_PENDING" if watch_pending else "COMPLETE"),"universe":total,"processed":done,"skipped":skipped,"failed":failed,"suspension_watch_pending":watch_pending,"database":str(a.db),"request_checked_through":end.isoformat(),"note":"Successful query coverage only, not proof of per-day trades or calendar completeness. Staging only; A/B/LINE unchanged"},ensure_ascii=False))
        if failed:raise SystemExit(2)
    finally:db.close()

if __name__=="__main__":main()
