#!/usr/bin/env python3
"""F15 capture-path readiness audit. Read-only, no imports of application modules."""
import ast,os,hashlib,collections,json
from pathlib import Path
ROOT=Path("/opt/render/project/src");P=Path("/var/data/stock-alert");F=P/"f15_eod"
TOK=("f15_eod","trajectory_v1","trajectory_raw_1m","production_event_snapshot","discover","handoff","estimated_vr5_parts","f10_baseline","candidate","monitor_loop")
def main():
 print("F15 EARLY HANDOFF CAPTURE READINESS | READ ONLY | NO NETWORK")
 py=sorted(ROOT.glob("*.py"))
 print("ROOT_PY_FILES",len(py))
 matches=[]
 for f in py:
  try:s=f.read_text(encoding="utf-8-sig")
  except (UnicodeError,OSError):continue
  hit=[(i,[k for k in TOK if k in line]) for i,line in enumerate(s.splitlines(),1) if any(k in line for k in TOK)]
  if hit:
   matches.append((f,s,hit))
   print("SOURCE",f.name,"SHA256",hashlib.sha256(f.read_bytes()).hexdigest(),"MATCHES",len(hit))
   for i,tags in hit[:30]:print(" REF",i,",".join(tags))
 print("MATCHING_SOURCE_FILES",len(matches))
 print("F15 ROOT ENTRIES:")
 if F.is_dir():
  for f in sorted(F.iterdir()):
   if f.is_file():print("FILE",f.name,"BYTES",f.stat().st_size)
   else:print("DIR",f.name)
 print("F15 MANIFEST SUMMARY:")
 for f in sorted(F.glob("trajectory_v1/20??-??-??/manifest.json")):
  try:
   x=json.loads(f.read_text());print("MANIFEST",f.parent.name,"KEYS",sorted(x) if isinstance(x,dict) else type(x).__name__)
  except (ValueError,OSError) as e:print("MANIFEST_UNREADABLE",f.parent.name,type(e).__name__)
 print("A/B SOURCE FUNCTION SIGNATURES:")
 for name in ("fugle_a_scanner_v2_4.py","b_runner.py","fugle_b_live_runner_v2_p1_final.py"):
  f=ROOT/name
  if not f.is_file():print("MISSING",name);continue
  try:tree=ast.parse(f.read_text(encoding="utf-8-sig"))
  except (SyntaxError,UnicodeError) as e:print("PARSE_ERROR",name,type(e).__name__);continue
  for n in ast.walk(tree):
   if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(k in n.name.lower() for k in ("discover","evaluate","monitor","scan","handoff","persist","estimate","run")):
    print("FUNC",name,n.name,n.lineno,n.end_lineno)
 print("LIMIT: identifies candidate capture paths only; no proof of hook timing or non-signal coverage.")
 print("NO WRITES; NO NETWORK; NO MODULE IMPORTS")
if __name__=="__main__":main()
