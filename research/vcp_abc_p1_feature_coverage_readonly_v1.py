#!/usr/bin/env python3
"""Read-only audit of B ABC/P1 signal identities and available contemporaneous volume features."""
import json, pathlib, collections, sqlite3
ROOT=pathlib.Path("/var/data/stock-alert/b_live_runner_v2_p1")
DB=pathlib.Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
START,END="2026-09-29","2026-10-08"
def stop(x): raise RuntimeError("STOP: "+x)
def main():
 print("ABC_P1_VCP_FEATURE_COVERAGE_V1 | READ ONLY | NO API | NO WRITES")
 if not ROOT.is_dir() or not DB.is_file():stop("missing input")
 rows=[]; kinds=collections.Counter(); keys=collections.defaultdict(collections.Counter)
 for dd in sorted(ROOT.iterdir()):
  if not dd.is_dir() or not START<=dd.name<=END:continue
  for sd in sorted(dd.iterdir()):
   if not sd.is_dir():continue
   present=[x for x in ("signal_event.json","p1_signal_event.json") if (sd/x).is_file()]
   if not present:continue
   m=sd/"canonical_minutes.jsonl"
   if not m.is_file():stop("missing minute "+str(sd))
   minute_rows=[json.loads(s) for s in m.read_text(encoding="utf-8").splitlines() if s.strip()]
   if not minute_rows:stop("empty minutes "+str(sd))
   times=[x.get("minute") for x in minute_rows]
   if any(x is None for x in times) or times!=sorted(set(times)):stop("minute identity "+str(sd))
   for x in minute_rows:
    if x.get("date")!=dd.name or str(x.get("stock_id"))!=sd.name:stop("minute stock/day mismatch "+str(sd))
   for f in present:
    obj=json.loads((sd/f).read_text(encoding="utf-8"))
    if not isinstance(obj,dict):stop("signal schema "+str(sd/f))
    if str(obj.get("stock_id"))!=sd.name or obj.get("date")!=dd.name:stop("signal stock/day mismatch "+str(sd/f))
    kinds[f]+=1
    for k in obj:keys[f][k]+=1
   rows.append((dd.name,sd.name,present,minute_rows))
 if len(rows)!=183:stop("cohort count changed "+str(len(rows))+" expected 183")
 print("COHORT_STOCK_DAYS",len(rows),"SIGNAL_FILES",dict(kinds))
 for f in ("signal_event.json","p1_signal_event.json"):
  print("SIGNAL_KEYS",f,",".join(sorted(keys[f])))
 print("MINUTE_KEYS",",".join(sorted(set().union(*(set(x.keys()) for _,_,_,rr in rows for x in rr[:1])))))
 with sqlite3.connect(f"file:{DB}?mode=ro",uri=True) as c:
  cols=[r[1] for r in c.execute("PRAGMA table_info(daily_ohlcv)")]
  print("DAILY_COLUMNS",",".join(cols))
  coverage=collections.Counter()
  for day,sid,present,rr in rows:
   hist=c.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE symbol=? AND day<?",(sid,day)).fetchone()[0]
   if hist>=5:coverage["PRIOR5"]+=1
   if hist>=60:coverage["PRIOR60"]+=1
   if c.execute("SELECT 1 FROM daily_ohlcv WHERE symbol=? AND day=?",(sid,day)).fetchone():coverage["DAY_CLOSE"]+=1
   for f in present:
    d=json.loads((ROOT/day/sid/f).read_text(encoding="utf-8"))
    ts=[(k,d.get(k)) for k in ("recognition_time","p1_time","a1_time","discovered_at","live_known_time") if d.get(k)]
    print("SIGNAL",day,sid,f,"class",d.get("signal_class"),"source",d.get("source"),"times",json.dumps(ts,ensure_ascii=False),"minute_end",rr[-1]["minute"])
  print("DAILY_COVERAGE",dict(coverage))
 print("IMPORTANT: This is a B-signal-selected cohort, NOT the all-market VCP or all-market B universe.")
 print("IMPORTANT: EVG availability/formula and ABC class identity require separate source-code audit.")
 print("STATUS PASS_COVERAGE_AUDIT_ONLY")
if __name__=="__main__":main()
