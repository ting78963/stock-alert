#!/usr/bin/env python3
"""Read-only F15 collector + A hook context audit. No imports, network, or writes."""
from pathlib import Path
import ast,hashlib
R=Path("/opt/render/project/src")
SPECS={
 "f15_trajectory_store.py":[(1,130)],
 "production_worker_v1.py":[(1,100)],
 "production_worker_v2_shared_ws.py":[(1,50),(270,335),(350,415)],
 "fugle_a_scanner_v2_4.py":[(130,170),(540,590),(1430,1490),(1515,1565),(1690,1765)],
 "main.py":[(1,45),(150,225)],
 "f15_eod_signal_report.py":[(1,100)]
}
SENSITIVE=("token","secret","password","authorization","api_key","line_channel","bearer")
def main():
 print("F15 HOOK CONTEXT | READ ONLY")
 for name,ranges in SPECS.items():
  p=R/name
  if not p.is_file():print("MISSING",name);continue
  data=p.read_bytes()
  try:src=data.decode("utf-8-sig");ast.parse(src)
  except Exception as e:print("PARSE_FAILED",name,type(e).__name__);continue
  lines=src.splitlines()
  print("\nFILE",name,"SHA256",hashlib.sha256(data).hexdigest(),"LINES",len(lines))
  for start,end in ranges:
   print("RANGE",start,min(end,len(lines)))
   for i in range(start,min(end,len(lines))+1):
    s=lines[i-1]
    if any(k in s.lower() for k in SENSITIVE):
     print(f"{i:04d} [REDACTED SENSITIVE LINE]")
    else:print(f"{i:04d} {s[:190]}")
 print("NO EXECUTION, NO NETWORK, NO WRITES")
if __name__=="__main__":main()
