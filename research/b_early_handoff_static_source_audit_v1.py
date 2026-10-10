#!/usr/bin/env python3
"""Static read-only inspection of B source files, no import/execute/network."""
import ast,hashlib,re
from pathlib import Path
FILES=[Path("/opt/render/project/src/b_runner.py"),Path("/opt/render/project/src/fugle_b_live_runner_v2_p1_final.py")]
TOKENS=("recogn","frontier","p1","signal","handoff","queue","dedup","sqlite","database","persist","insert","commit","line","notify","http","requests","api","minute","kbar","histor","cache","argparse","main","runner","import")
def stop(msg):raise SystemExit("AUDIT STOP: "+msg)
def main():
 for f in FILES:
  if not f.is_file():stop("missing "+str(f))
  raw=f.read_bytes()
  try:s=raw.decode("utf-8-sig");tree=ast.parse(s,filename=str(f))
  except Exception as e:stop(f"cannot parse {f.name}: {type(e).__name__} {e}")
  lines=s.splitlines()
  print("\n"+"="*90)
  print("SOURCE",f,"LINES",len(lines),"SHA256",hashlib.sha256(raw).hexdigest())
  print("TOP LEVEL:")
  for node in tree.body:
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
    print(type(node).__name__,node.name,"lines",node.lineno,"-",node.end_lineno)
   elif isinstance(node,(ast.Import,ast.ImportFrom)):
    print("IMPORT",node.lineno,ast.get_source_segment(s,node).splitlines()[0][:160])
  print("RELEVANT DEFINITIONS:")
  for node in ast.walk(tree):
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
    name=node.name.lower()
    if any(k in name for k in TOKENS):
     print("FUNCTION",node.name,"lines",node.lineno,"-",node.end_lineno,"args",",".join(a.arg for a in node.args.args)[:140])
  print("KEYWORD MATCHES (capped 100, redact secrets and literals):")
  n=0
  for i,line in enumerate(lines,1):
   if any(k in line.lower() for k in TOKENS):
    # Only line numbers and token labels: do not print credentials or environment values.
    tags=[k for k in TOKENS if k in line.lower()]
    print("LINE",i,"TOKENS",",".join(tags[:10]))
    n+=1
    if n>=100:
     print("TRUNCATED keyword matches");break
  print("ENTRYPOINT GUARDS:")
  for node in tree.body:
   if isinstance(node,ast.If) and "__name__" in ast.unparse(node.test):
    print("IF_MAIN",node.lineno,"-",node.end_lineno)
 print("\nSTATIC INSPECTION ONLY. No imports, B executions, API calls, or writes.")
if __name__=="__main__":main()
