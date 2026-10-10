#!/usr/bin/env python3
"""F15 storage and duplication audit. Read-only; no network, no production writes."""
import json,collections,os,sqlite3
from pathlib import Path
P=Path("/var/data/stock-alert")
F=P/"f15_eod"
def main():
 print("F15 STORAGE AUDIT | READ ONLY | NO NETWORK")
 if not F.is_dir():raise SystemExit("AUDIT STOP: F15 root absent")
 print("F15_ROOT",F)
 files=[]
 for root,dirs,names in os.walk(F):
  dirs[:]=[d for d in dirs if not d.startswith(".")]
  for n in names:
   p=Path(root)/n
   if p.is_file():files.append(p)
 print("FILES",len(files),"BY_SUFFIX",dict(collections.Counter(p.suffix.lower() or "(none)" for p in files)))
 print("DIRECTORIES (depth<=3, file count):")
 counts=collections.Counter(str(p.parent.relative_to(F)) for p in files)
 for d,n in sorted(counts.items()):
  if len(Path(d).parts)<=3:print("DIR",d,"FILES",n)
 fs=sorted(F.glob("trajectory_v1/20??-??-??/*.json"))
 print("TRAJECTORY_FILES",len(fs))
 identity=collections.Counter();stockday=collections.Counter();keys=collections.Counter();trajkeys=collections.Counter();errors=[]
 for p in fs:
  try:
   obj=json.loads(p.read_text(encoding="utf-8"))
   i=obj["identity"];date=str(i["date"]);stock=str(i["stock_id"]);typ=str(i["signal_class"]);tm=str(i["recognition_time"])
   identity[(date,stock,typ,tm)]+=1;stockday[(date,stock)]+=1
   keys.update(obj.keys())
   raw=obj.get("trajectory_raw_1m",[])
   if isinstance(raw,list) and raw and isinstance(raw[0],dict):trajkeys.update(raw[0].keys())
  except Exception as e:errors.append((str(p.relative_to(F)),type(e).__name__))
 print("IDENTITIES",len(identity),"DUPLICATE_IDENTITIES",sum(v-1 for v in identity.values() if v>1))
 print("UNIQUE_STOCK_DAYS",len(stockday),"MULTI_SIGNAL_STOCK_DAYS",sum(v>1 for v in stockday.values()))
 print("TOP_LEVEL_KEYS",sorted(keys))
 print("TRAJECTORY_1M_KEYS",sorted(trajkeys))
 print("MULTI_SIGNAL_EXAMPLES (max 15):")
 for (d,s),v in sorted(stockday.items()):
  if v>1:
   print("STOCK_DAY",d,s,"SIGNALS",v)
   if sum(1 for x in stockday.values() if x>1)>100:break
 print("PARSE_ERRORS",len(errors),errors[:5])
 print("RELEVANT_DB_SCHEMA (names and columns only):")
 for db in sorted(P.glob("*.sqlite3")):
  if not any(t in db.name.lower() for t in ("f15","f10","signal","handoff","canonical")):continue
  try:
   cx=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True)
   names=[r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
   print("DB",db.name,"TABLES",names[:30])
   for name in names[:20]:
    if any(k in name.lower() for k in ("f15","signal","handoff","event","candidate","f10")):
     cols=[r[1] for r in cx.execute("PRAGMA table_info('"+name.replace("'","''")+"')")]
     print("TABLE",name,"COLUMNS",cols[:40])
   cx.close()
  except (sqlite3.Error,OSError) as e:print("DB_UNAVAILABLE",db.name,type(e).__name__)
 print("DONE | READ ONLY")
if __name__=="__main__":main()
