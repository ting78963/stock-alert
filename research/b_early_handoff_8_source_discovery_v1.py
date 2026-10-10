#!/usr/bin/env python3
"""B replay prerequisite audit. Read-only; metadata only; no API or B execution."""
import json,sqlite3,os
from pathlib import Path
from collections import Counter
P=Path("/var/data/stock-alert")
R=P/"_research_output/f15_174_api_800_1000_v1/results_174_and_v3.json"
TARGETS={"2485","3042","1714","8358","1326","2455","2340","2032"}
def stop(s):raise SystemExit("AUDIT STOP: "+s)
def main():
 if not R.is_file():stop("missing strict AND results")
 rows=json.loads(R.read_text())
 if len(rows)!=174:stop("identity count !=174")
 hits=[r for r in rows if r.get("first_1000") is not None]
 if len(hits)!=69 or len({(r["date"],r["stock_id"]) for r in hits})!=68:stop("strict AND sample identity mismatch")
 chosen=[r for r in hits if r["stock_id"] in TARGETS]
 if len({r["stock_id"] for r in chosen})!=8:stop("target coverage mismatch")
 print("AUDIT PASS: 174 identities, 69 early signals, 68 unique stock-days")
 print("TARGETS (all dates matching 8 stock IDs):")
 for r in chosen:print(r["date"],r["stock_id"],r["class"],f'{r["first_1000"]//60:02d}:{r["first_1000"]%60:02d}',r["recognition"],r["lead_1000"])
 print("B SOURCE CANDIDATES (filename only; no import, no execute):")
 roots=[Path.cwd(),P]
 found=[]
 for root in roots:
  if not root.exists():continue
  for pat in ("*b*runner*.py","*b*recogn*.py","*B*runner*.py","*B*recogn*.py","*handoff*.py","*canonical*.py"):
   for f in root.glob(pat):
    if f.is_file():found.append(str(f))
 for f in sorted(set(found))[:80]:print("FILE",f)
 print("B DATA CANDIDATES (filename, size only; limited depth):")
 dirs=[P,P/"_research_output",P/"f15_eod",Path.cwd()]
 seen=set()
 for root in dirs:
  if not root.is_dir():continue
  try: entries=list(root.iterdir())
  except OSError:continue
  for f in entries:
   if f.is_file() and f.suffix.lower() in (".sqlite3",".db",".jsonl",".csv") and any(k in f.name.lower() for k in ("b_","signal","handoff","canonical","f15","runner","event")):
    if str(f) not in seen:
     seen.add(str(f));print("DATA",f.name,"bytes",f.stat().st_size,"path",f.parent)
 print("SQLITE SCHEMA (table names + column names only, no row content):")
 for db in sorted(P.glob("*.sqlite3")):
  if not any(k in db.name.lower() for k in ("signal","b_","canonical","f15","live","history","handoff")):continue
  try:
   cx=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
   names=[x[0] for x in cx.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
   for name in names:
    if any(k in name.lower() for k in ("signal","handoff","b_","recogn","event","queue","candidate","canonical")):
     cols=[x[1] for x in cx.execute("PRAGMA table_info('"+name.replace("'","''")+"')")]
     print("TABLE",db.name,name,"COLUMNS",",".join(cols[:40]))
   cx.close()
  except (sqlite3.Error,OSError) as e:print("DB_UNAVAILABLE",db.name,type(e).__name__)
 print("LIMIT: this is source discovery only, not B recognition replay.")
 print("LIMIT: absence in these directories does not prove B logs do not exist elsewhere.")
if __name__=="__main__":main()
