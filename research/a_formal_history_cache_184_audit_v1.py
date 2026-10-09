#!/usr/bin/env python3
"""F15 184 identities versus formal A persisted EstimatedVR5 cache. READ ONLY."""
import json,collections,math,sqlite3
from pathlib import Path
P=Path("/var/data/stock-alert")
ROOT=P/"f15_eod/trajectory_v1"
fs=sorted(x for x in ROOT.glob("20??-??-??/*.json") if x.name!="manifest.json")
if not fs: raise SystemExit("AUDIT STOP: no F15 files")
# Match production A HISTORY_CACHE_FILE (code-relative), and inspect persistent candidate separately.
import importlib.util,sys
src=Path.cwd()/"fugle_a_scanner_v2_4.py"
if not src.exists(): raise SystemExit("AUDIT STOP: formal A source not found")
spec=importlib.util.spec_from_file_location("formal_a_cache_audit",src)
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
paths=[mod.HISTORY_CACHE_FILE,P/"a_history_cache_v2_4.json"]
print("FORMAL A CACHE COVERAGE | READ ONLY | NO API | NO WRITES")
print("FORMAL_A_CACHE_PATH",mod.HISTORY_CACHE_FILE)
print("F15_FILES",len(fs))
identities=[]; seen=set()
for f in fs:
 try:
  x=json.loads(f.read_text())["identity"]
  d=str(x["date"]);s=str(x["stock_id"]);c=str(x["signal_class"]);t=str(x["recognition_time"])
  k=(d,s,c,t)
  assert d==f.parent.name and c in ("A","B","C","P1") and k not in seen
  seen.add(k);identities.append((d,s,c))
 except Exception as e: raise SystemExit("AUDIT STOP: F15 identity "+str(f)+" "+str(e))
print("IDENTITY_PASS",len(identities))
for path in dict.fromkeys(paths):
 print("CACHE_PATH",path,"EXISTS",path.is_file())
 if not path.is_file():continue
 try: cache=json.loads(path.read_text())
 except Exception as e:raise SystemExit("AUDIT STOP: invalid cache "+str(e))
 if not isinstance(cache,dict):raise SystemExit("AUDIT STOP: cache not dict")
 counts=collections.Counter();byday=collections.defaultdict(collections.Counter);byclass=collections.defaultdict(collections.Counter)
 for d,s,c in identities:
  k=f"estvr5|{s}|{d}"; v=cache.get(k)
  if not isinstance(v,list):status="NO_ESTVR5_KEY"
  elif len(v)<5:status="LT5"
  else:
   try:
    dates=[str(x["date"]) for x in v]
    assert len(dates)==len(set(dates)) and all(z<d for z in dates)
    for x in v:
     assert math.isfinite(float(x["full"])) and float(x["full"])>0
     pts=x["pts"];assert isinstance(pts,list) and pts
     last=-1.0
     for pt in pts:
      assert len(pt)==2 and math.isfinite(float(pt[1])) and float(pt[1])>=last
      last=float(pt[1])
     assert abs(last-float(x["full"]))<=1e-9
    status="VALID_10_PLUS" if len(v)>=10 else "VALID_5_TO_9"
   except Exception as e:raise SystemExit("AUDIT STOP: corrupt cache "+k+" "+repr(e))
  counts[status]+=1;byday[d][status]+=1;byclass[c][status]+=1
 print("CACHE_KEYS",len(cache),"COVERAGE",dict(counts))
 for d in sorted(byday):print("DAY",d,dict(byday[d]))
 for c in sorted(byclass):print("CLASS",c,dict(byclass[c]))
 print("LIMIT: cache currently present does not prove availability at recognition time")
print("DONE")
