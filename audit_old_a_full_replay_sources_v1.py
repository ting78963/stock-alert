#!/usr/bin/env python3
"""Read-only preflight for full old-A replay; inspect coverage, not infer missing inputs."""
import sqlite3,json,pathlib,collections,sys
P=pathlib.Path("/var/data/stock-alert")
CANDIDATES=[
 P/"backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3",
 P/"f10_baseline_v1.sqlite3",
 P/"shared_history_stage_v1.sqlite3",
 P/"a_f11_metadata_v1.json",
 P/"a_scan_mother",
 P/"a_queue_shadow_audit",
 P/"b_live_runner_v2_p1",
 P/"_research_output",
]
def describe(path):
 print("\nPATH",path,"EXISTS",path.exists(),"TYPE",("DIR" if path.is_dir() else "FILE" if path.is_file() else "MISSING"))
 if not path.exists():return
 if path.is_dir():
  try:
   children=sorted(path.iterdir(),key=lambda x:x.name)
   print("CHILDREN_COUNT",len(children),"FIRST_12",[x.name for x in children[:12]])
  except Exception as e:print("INSPECT_ERROR",repr(e))
  return
 if path.suffix==".json":
  try:
   with path.open(encoding="utf-8") as f: obj=json.load(f)
   print("JSON_ROOT",type(obj).__name__,"LENGTH",len(obj) if hasattr(obj,"__len__") else "NA")
   if isinstance(obj,dict):
    print("TOP_KEYS",list(obj)[:25])
    if obj:
     val=next(iter(obj.values()))
     print("FIRST_VALUE_TYPE",type(val).__name__,"FIRST_VALUE_KEYS",list(val)[:25] if isinstance(val,dict) else "NA")
  except Exception as e:print("JSON_ERROR",repr(e))
  return
 if path.suffix not in (".sqlite3",".db"):return
 try:
  con=sqlite3.connect(f"file:{path}?mode=ro",uri=True)
  print("DB_INTEGRITY",con.execute("PRAGMA quick_check").fetchone()[0])
  names=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  print("TABLES",names[:45],"TOTAL",len(names))
  for name in names:
   if name.startswith("sqlite_"):continue
   quoted='"'+name.replace('"','""')+'"'
   cols=[(r[1],r[2]) for r in con.execute(f"PRAGMA table_info({quoted})")]
   print("TABLE",name,"COLUMNS",cols[:35])
   if name in ("f10_day","daily_ohlcv"):
    print("ROWS",con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
    rows=con.execute(f"SELECT * FROM {quoted} LIMIT 1").fetchall()
    if rows:
     keys=[c[0] for c in con.execute(f"SELECT * FROM {quoted} LIMIT 0").description]
     sample=dict(zip(keys,rows[0]))
     for k,v in sample.items():
      if isinstance(v,str) and len(v)>250:
       if k=="pts_json":
        try:
         a=json.loads(v)
         print("SAMPLE",k,"len",len(a),"first",a[:2] if isinstance(a,list) else str(type(a)))
        except Exception as e:print("SAMPLE",k,"json error",str(e))
       else:print("SAMPLE",k,"<long string>",len(v))
      else:print("SAMPLE",k,repr(v)[:250])
  con.close()
 except Exception as e:print("DB_ERROR",repr(e))
print("OLD A FULL REPLAY | SOURCE COVERAGE PREFLIGHT | READ ONLY")
for path in CANDIDATES:describe(path)
print("\nREQUIRED: historical minute-level price+volume; prior D-1 price/volume; F10 causal curve; metadata industry/security; price MA20; signal/queue logs.")
print("NOTE: existence/columns do not prove causal replay availability. No candidate counts or performance are computed.")
print("PASS | NO NETWORK | NO PRODUCTION WRITE")
