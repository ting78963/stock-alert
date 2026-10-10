#!/usr/bin/env python3
"""Audit strict-AND 174 results against OR baseline, no API or production writes."""
import json, statistics
from collections import Counter
from pathlib import Path
P=Path("/var/data/stock-alert/_research_output/f15_174_api_800_1000_v1")
def stop(msg):raise SystemExit("AUDIT STOP: "+msg)
def minute(s):
 h,m=map(int,str(s)[:5].split(":"));return h*60+m
def main():
 a=P/"results_174_and_v3.json";b=P/"results_174_skip404_v2.json"
 if not a.is_file() or not b.is_file():stop("missing completed result file")
 strict=json.loads(a.read_text());loose=json.loads(b.read_text())
 if len(strict)!=174 or len(loose)!=174:stop("expected 174 identities each")
 keys=lambda r:(r["date"],r["stock_id"],r["class"],r["recognition"])
 if [keys(r) for r in strict]!=[keys(r) for r in loose]:stop("v2/v3 identity/order mismatch")
 if len(set(map(keys,strict)))!=174:stop("duplicate signal identity")
 miss=[r for r in strict if r.get("status")=="MISSING_HISTORY"]
 if len(miss)!=1:stop("unexpected missing-history count")
 for x,y in zip(strict,loose):
  if (x.get("status")=="MISSING_HISTORY")!=(y.get("status")=="MISSING_HISTORY"):stop("missing mismatch")
  for th in (800,1000):
   c=f"first_{th}";z=x.get(c);old=y.get(c)
   if z is not None and (old is None or z<old):stop(f"AND not subset of OR {keys(x)} {th}")
   if z is not None and (minute(x["recognition"])-z)!=x.get(f"lead_{th}"):stop("lead mismatch")
   if z is not None and z>=minute(x["recognition"]):stop("not early")
   if th==1000 and z is not None and x.get("first_800") is None:stop("1000 not subset of 800")
 valid=[r for r in strict if r.get("status")!="MISSING_HISTORY"]
 hit=[r for r in valid if r.get("first_1000") is not None]
 early800=[r for r in valid if r.get("first_800") is not None]
 print("AUDIT PASS | total=174 complete=173 missing=1")
 print(f"STRICT AND: 800={len(early800)} 1000={len(hit)}")
 print("1000 CLASS:",dict(Counter("P1" if r["class"]=="P1" else "ABC" for r in hit)))
 print("1000 by day:",dict(sorted(Counter(r["date"] for r in hit).items())))
 unique={(r["date"],r["stock_id"]) for r in hit}
 print(f"1000 UNIQUE STOCK-DAY={len(unique)} SIGNAL IDENTITIES={len(hit)}")
 print("800 ONLY:")
 for r in early800:
  if r.get("first_1000") is None:print(r["date"],r["stock_id"],r["class"],"lead800",r["lead_800"])
 print("1000 DETAIL: date stock class AND_time original_time lead_min OR_time")
 for r in sorted(hit,key=lambda r:(r["date"],r["first_1000"],r["stock_id"])):
  t=r["first_1000"];ot=next(z["first_1000"] for z in loose if keys(z)==keys(r))
  fmt=lambda n:f"{n//60:02d}:{n%60:02d}" if n is not None else "-"
  print(r["date"],r["stock_id"],r["class"],fmt(t),r["recognition"],r["lead_1000"],fmt(ot))
 print("LIMIT: earliest B recognition cannot be inferred from these A-handoff snapshots.")
 print("LIMIT: full-market B load and prior B enrollment not present.")
if __name__=="__main__":main()
