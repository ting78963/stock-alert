#!/usr/bin/env python3
"""Read-only F10 projection audit for F15 shadow A.
Replicates production A F10 curve semantics; no Fugle/API, no production writes.
"""
import argparse,bisect,datetime as dt,json,math,os,sqlite3,tempfile
from pathlib import Path
def calc(days,cutoff):
 if len(days)!=10:raise ValueError("need 10 validated F10 days; fail closed")
 fulls=[];curves=[];dates=[]
 for day,full,raw in days:
  if day in dates:raise ValueError("duplicate date")
  dates.append(day)
  pts=json.loads(raw) if isinstance(raw,str) else raw
  if not pts or not math.isfinite(float(full)) or float(full)<=0:raise ValueError("invalid day")
  ts=[];vs=[];prev=-1
  for t,v in pts:
   t=str(t);v=float(v)
   if (ts and t<=ts[-1]) or not math.isfinite(v) or v<prev or v<0:raise ValueError("invalid curve")
   ts.append(t);vs.append(v);prev=v
  if abs(prev-float(full))>1e-9:raise ValueError("curve/full mismatch")
  fulls.append(float(full));curves.append((ts,vs))
 if dates!=sorted(dates):raise ValueError("unsorted dates")
 cut=str(cutoff)
 if len(cut)==5:cut+=":00"
 fractions=[]
 for (ts,vs),full in zip(curves,fulls):
  idx=bisect.bisect_right(ts,cut)-1
  fractions.append((vs[idx] if idx>=0 else 0)/full)
 f10=sum(fractions)/len(fractions)
 if not 0<f10<=1+1e-8:raise ValueError("invalid f10")
 return {"f10":f10,"prior5_avg":sum(fulls[-5:])/5,"prior1":fulls[-1],"days":dates}
def from_db(db,symbol,date,minute,volume):
 if not (symbol.isdigit() and 4<=len(symbol)<=6):raise ValueError("invalid stock")
 dt.date.fromisoformat(date);dt.time.fromisoformat(minute)
 if not math.isfinite(volume) or volume<0:raise ValueError("invalid volume")
 uri="file:"+str(Path(db).resolve())+"?mode=ro"
 with sqlite3.connect(uri,uri=True,timeout=2) as con:
  rows=con.execute("SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10",(symbol,date)).fetchall()
 rows=list(reversed(rows))
 out=calc(rows,minute)
 projected=volume/out["f10"]
 return {"stock_id":symbol,"date":date,"market_minute":minute,"cum_volume_zhang":volume,
         "f10":out["f10"],"projected_zhang":projected,"evg5":projected/out["prior5_avg"],
         "evg1":projected/out["prior1"],"baseline_days":out["days"],
         "eligible":volume>=1000 and projected/out["prior5_avg"]>=2.5 and projected/out["prior1"]>=2.5,
         "source":"F10_SQLITE_READ_ONLY","status":"HISTORICAL_BASELINE_ONLY_NOT_LIVE"}
def selftest():
 with tempfile.TemporaryDirectory() as root:
  db=Path(root)/"test.sqlite3"
  with sqlite3.connect(db) as con:
   con.execute("CREATE TABLE f10_day(symbol TEXT,day TEXT,full REAL,pts_json TEXT)")
   for n in range(10):
    day=(dt.date(2026,9,20)+dt.timedelta(days=n)).isoformat()
    con.execute("INSERT INTO f10_day VALUES(?,?,?,?)",("1326",day,2000,json.dumps([["09:00:00",100],["09:10:00",400],["13:30:00",2000]])))
  r=from_db(db,"1326","2026-10-01","09:10",1100)
  assert abs(r["f10"]-.2)<1e-12 and abs(r["projected_zhang"]-5500)<1e-8
  assert abs(r["evg5"]-2.75)<1e-12 and r["eligible"]
  assert not from_db(db,"1326","2026-10-01","09:10",999)["eligible"]
  try:from_db(db,"9999","2026-10-01","09:10",1100);raise AssertionError("missing accepted")
  except ValueError:pass
 print("PASS | F10 10-day cutoff, projected volume, EVG5/EVG1, strict AND, missing history STOP")
 print("NO NETWORK | NO PRODUCTION WRITES | NOT LIVE CAPTURE")
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--selftest",action="store_true")
 ap.add_argument("--db");ap.add_argument("--symbol");ap.add_argument("--date");ap.add_argument("--minute");ap.add_argument("--volume",type=float)
 a=ap.parse_args()
 if a.selftest:selftest();return
 if not all((a.db,a.symbol,a.date,a.minute,a.volume is not None)):ap.error("use --selftest or all --db --symbol --date --minute --volume")
 print(json.dumps(from_db(a.db,a.symbol,a.date,a.minute,a.volume),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
