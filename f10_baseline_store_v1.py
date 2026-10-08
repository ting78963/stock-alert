#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent rolling F10 volume baseline store. One range request per symbol on cold init."""
import argparse,json,os,sqlite3,time,urllib.error,urllib.parse,urllib.request
from collections import defaultdict
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from twse_session_gate_v1 import is_scheduled_open

TZ=ZoneInfo("Asia/Taipei")
BASE="https://api.fugle.tw/marketdata/v1.0/stock"
ROOT=Path(os.environ.get("PRODUCTION_STATE_DIR",Path(__file__).resolve().parent/"_production_output"))
DB=ROOT/"f10_baseline_v1.sqlite3"
SEED=Path(__file__).resolve().parent/"f10_permanent_seed_v1.json"

def api_key():
    k=os.environ.get("FUGLE_API_KEY","").strip()
    if not k: raise RuntimeError("FUGLE_API_KEY missing")
    return k

def db():
    ROOT.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS member(symbol TEXT PRIMARY KEY, added_at TEXT NOT NULL, source TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS f10_day(symbol TEXT NOT NULL, day TEXT NOT NULL, full REAL NOT NULL, pts_json TEXT NOT NULL, PRIMARY KEY(symbol,day))")
    c.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_f10_symbol_day ON f10_day(symbol,day)")
    c.commit(); return c

def seed_members(c):
    x=json.loads(SEED.read_text(encoding="utf-8")); syms=[str(s).zfill(4) for s in x["symbols"]]
    if not syms or len(syms)!=len(set(syms)) or len(syms)!=x.get("count"): raise RuntimeError("SEED AUDIT FAILED: count/uniqueness mismatch")
    now=datetime.now(TZ).isoformat(timespec="seconds")
    c.executemany("INSERT OR IGNORE INTO member(symbol,added_at,source) VALUES(?,?,?)",[(s,now,"seed435") for s in syms]); c.commit()
    n=c.execute("SELECT COUNT(*) FROM member").fetchone()[0]
    print(f"[F10 MEMBERS] seed={len(syms)} permanent_total={n}",flush=True)

def fetch(symbol,fr,to,key):
    q=urllib.parse.urlencode({"timeframe":"1","from":fr,"to":to,"fields":"volume","sort":"asc"})
    u=f"{BASE}/historical/candles/{urllib.parse.quote(symbol)}?{q}"
    req=urllib.request.Request(u,headers={"X-API-KEY":key,"User-Agent":"f10-baseline-v1/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:return json.loads(r.read().decode())

def parse(symbol,obj,to_day):
    if str(obj.get("symbol") or "")!=symbol: raise RuntimeError(f"{symbol} identity mismatch")
    if str(obj.get("timeframe") or "")!="1": raise RuntimeError(f"{symbol} timeframe mismatch")
    rows=obj.get("data")
    if not isinstance(rows,list): raise RuntimeError(f"{symbol} missing data[]")
    by=defaultdict(list)
    for x in rows:
        raw=str(x.get("date") or "")
        if len(raw)<16: continue
        ds=raw[:10]
        if ds>to_day: raise RuntimeError(f"{symbol} future leakage {ds}>{to_day}")
        tm=raw[11:19]; v=float(x.get("volume") or 0)
        if v<0: raise RuntimeError(f"{symbol} negative volume")
        by[ds].append((tm,v))
    out=[]
    for ds,xs in sorted(by.items()):
        seen=set(); full=0.; pts=[]
        for tm,v in sorted(xs):
            if tm in seen: raise RuntimeError(f"{symbol} duplicate minute {ds} {tm}")
            seen.add(tm); full+=v; pts.append([tm,full])
        if full>0 and pts: out.append((ds,full,pts))
    return out

def trim(c,symbol):
    days=[r[0] for r in c.execute("SELECT day FROM f10_day WHERE symbol=? ORDER BY day DESC",(symbol,)).fetchall()]
    for ds in days[11:]: c.execute("DELETE FROM f10_day WHERE symbol=? AND day=?",(symbol,ds))

def backfill_older(c,symbol,key,pause):
    """Fill missing slots using older positive-volume sessions; preserve existing rows."""
    have=[r[0] for r in c.execute("SELECT day FROM f10_day WHERE symbol=? ORDER BY day",(symbol,))]
    if not have or len(have)>=11: return 0
    cursor=date.fromisoformat(have[0])-timedelta(days=1)
    added=0
    # Bounded 24-calendar-day windows, at most four per maintenance run.
    for _ in range(4):
        if len(have)>=11: break
        start=cursor-timedelta(days=23)
        try:
            older=parse(symbol,fetch(symbol,start.isoformat(),cursor.isoformat(),key),cursor.isoformat())
        except urllib.error.HTTPError as e:
            print(f"[F10 BACKFILL STOP] {symbol} HTTP {e.code}",flush=True)
            break
        except Exception as e:
            print(f"[F10 BACKFILL STOP] {symbol} {type(e).__name__}: {e}",flush=True)
            break
        for ds,full,pts in reversed(older):
            if len(have)>=11: break
            if ds in have: continue
            if not pts or abs(pts[-1][1]-full)>0.0001:
                print(f"[F10 BACKFILL STOP] {symbol} volume integrity {ds}",flush=True)
                return added
            c.execute("INSERT OR IGNORE INTO f10_day(symbol,day,full,pts_json) VALUES(?,?,?,?)",
                      (symbol,ds,full,json.dumps(pts,separators=(",",":"))))
            if c.execute("SELECT changes()").fetchone()[0]:
                have.insert(0,ds); added+=1
        c.commit()
        cursor=start-timedelta(days=1)
        if len(have)<11: time.sleep(max(0.75,pause))
    if added: print(f"[F10 BACKFILL] {symbol} added={added} sessions={len(have)}",flush=True)
    return added

def build(mode,pause):
    now=datetime.now(TZ); today=now.date()
    try:
        if not is_scheduled_open(today):
            print(f"[F10 SKIP] {today.isoformat()} TWSE non-trading day; no Fugle requests",flush=True)
            return 0
    except Exception as e:
        print(f"[F10 SESSION AUDIT FAILED] {type(e).__name__}: {e}; no Fugle requests",flush=True)
        return 2
    c=db(); seed_members(c); key=api_key(); to=(today if (now.hour,now.minute)>=(14,30) else today-timedelta(days=1)).isoformat()
    syms=[r[0] for r in c.execute("SELECT symbol FROM member ORDER BY symbol")]
    ok=skip=fail=http429s=0
    for i,s in enumerate(syms,1):
        have=[r[0] for r in c.execute("SELECT day FROM f10_day WHERE symbol=? ORDER BY day",(s,)).fetchall()]
        if mode=="init" and len(have)>=10:
            skip+=1; continue
        fr=(today-timedelta(days=24)).isoformat() if not have else (date.fromisoformat(have[-1])+timedelta(days=1)).isoformat()
        if fr>to: skip+=1; continue
        tries=0
        while True:
            try:
                obj=fetch(s,fr,to,key); days=parse(s,obj,to)
                for ds,full,pts in days:
                    c.execute("INSERT OR REPLACE INTO f10_day(symbol,day,full,pts_json) VALUES(?,?,?,?)",(s,ds,full,json.dumps(pts,separators=(",",":"))))
                trim(c,s); c.commit()
                n=c.execute("SELECT COUNT(*) FROM f10_day WHERE symbol=?",(s,)).fetchone()[0]
                if n<5: raise RuntimeError(f"{s} valid sessions <5 ({n})")
                ok+=1; print(f"[F10] {i}/{len(syms)} {s} sessions={n} range={fr}..{to}",flush=True); break
            except urllib.error.HTTPError as e:
                if e.code==429 and tries<8:
                    tries+=1;http429s+=1;wait=min(5*tries,30);print(f"[F10 429] {s} wait={wait}s try={tries}",flush=True);time.sleep(wait);continue
                fail+=1;print(f"[F10 FAIL] {s} HTTP {e.code}",flush=True);break
            except Exception as e:
                fail+=1;print(f"[F10 FAIL] {s} {type(e).__name__}: {e}",flush=True);break
        # Backfill only incomplete symbols, after normal forward maintenance.
        if mode=="update":
            count=c.execute("SELECT COUNT(*) FROM f10_day WHERE symbol=?",(s,)).fetchone()[0]
            if 0<count<11: backfill_older(c,s,key,pause)
        time.sleep(max(0,pause))
    complete=c.execute("SELECT COUNT(*) FROM (SELECT symbol FROM f10_day GROUP BY symbol HAVING COUNT(*)>=5)").fetchone()[0]
    total=c.execute("SELECT COUNT(*) FROM member").fetchone()[0]
    c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_run',?)",(datetime.now(TZ).isoformat(timespec="seconds"),));c.commit()
    print(f"[F10 DONE] members={total} complete_ge5={complete} ok={ok} skip={skip} fail={fail} http429={http429s} db={DB}",flush=True)
    return 0 if complete==total and fail==0 else 2

def audit():
    c=db();seed_members(c)
    total=c.execute("SELECT COUNT(*) FROM member").fetchone()[0]
    rows=c.execute("SELECT symbol,COUNT(*),MIN(day),MAX(day) FROM f10_day GROUP BY symbol ORDER BY symbol").fetchall()
    bad=[x for x in rows if x[1]<5 or x[1]>11]
    print(f"[AUDIT] members={total} with_data={len(rows)} bad_session_count={len(bad)} db={DB}")
    print(f"[AUDIT] db_bytes={DB.stat().st_size if DB.exists() else 0}")
    return 0 if total==len(rows) and not bad else 2

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--mode",choices=["init","update","audit"],default="init");p.add_argument("--pause",type=float,default=0.15);a=p.parse_args()
    raise SystemExit(audit() if a.mode=="audit" else build(a.mode,a.pause))
