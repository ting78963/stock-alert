#!/usr/bin/env python3
"""Old A full replay source coverage phase 2. READ ONLY. No network."""
from pathlib import Path
import sqlite3,json,collections
ROOT=Path("/var/data/stock-alert")
def safe(v,n=220):return repr(v)[:n]
def sample_dir(p):
 print("\nDIR",p,"exists",p.is_dir())
 if not p.is_dir():return
 ds=sorted(p.iterdir())
 for d in ds[:3]+ds[-2:]:
  print(" ENTRY",d.name,"dir",d.is_dir())
  if d.is_dir():
   for f in sorted(d.iterdir())[:8]:
    print("  FILE",f.name,"bytes",f.stat().st_size if f.is_file() else "dir")
    if f.is_file() and f.suffix in (".json",".jsonl",".csv"):
     try:
      with f.open(encoding="utf-8") as h:
       line=h.readline().strip()
      print("   FIRST_LINE",safe(line,420))
     except Exception as e:print("   READ_ERROR",str(e))
def db_stats(p):
 if not p.is_file():return
 con=sqlite3.connect(f"file:{p}?mode=ro",uri=True)
 for t in ("f10_day","daily_ohlcv"):
  if t not in [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]:continue
  print("\nDB",p.name,"TABLE",t)
  print("DAY_RANGE",con.execute(f"SELECT MIN(day),MAX(day),COUNT(DISTINCT day),COUNT(DISTINCT symbol) FROM {t}").fetchone())
  for d,n in con.execute(f"SELECT day,COUNT(*) FROM {t} GROUP BY day ORDER BY day DESC LIMIT 15"):print(" DAY",d,n)
  if t=="f10_day":
   for sym,day,full,pts in con.execute("SELECT symbol,day,full,pts_json FROM f10_day ORDER BY day DESC LIMIT 2"):
    try:
     a=json.loads(pts)
     print(" PTS_SAMPLE",sym,day,"full",full,"n",len(a),"first",a[:3],"last",a[-3:])
    except Exception as e:print(" PTS_ERROR",str(e))
 con.close()
print("OLD A FULL REPLAY | SOURCE COVERAGE PHASE 2 | READ ONLY")
db_stats(ROOT/"f10_baseline_v1.sqlite3")
db_stats(ROOT/"shared_history_stage_v1.sqlite3")
p=ROOT/"a_f11_metadata_v1.json"
if p.is_file():
 a=json.loads(p.read_text(encoding="utf-8")); s=a.get("symbols",{})
 print("\nF11_SYMBOL_COUNT",len(s),"SAMPLE",[(k,s[k]) for k in list(s)[:3]])
 print("F11_SAMPLE_KEYS",sorted({k for v in list(s.values())[:50] if isinstance(v,dict) for k in v}))
for d in ("a_scan_mother","b_live_runner_v2_p1","_research_output"):sample_dir(ROOT/d)
for p in (Path("/var/data/stock-alert"),Path("/var/data/stock-alert/backups"),Path("/var/data/stock-alert/_research_output")):
 print("\nTOP_FILES",p)
 if p.is_dir():
  for f in sorted(p.iterdir())[:100]:
   if f.is_file() and (f.suffix in (".sqlite3",".db",".json",".jsonl") or any(x in f.name.lower() for x in ("minute","kbar","tick","f10","price"))):print(" FILE",f.name,"bytes",f.stat().st_size)
print("\nPASS | INVENTORY ONLY | NO REPLAY, NO NETWORK, NO WRITE")
