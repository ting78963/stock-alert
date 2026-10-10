#!/usr/bin/env python3
"""Audit whether A's existing estimation path can support F15 shadow capture.
Read-only static audit + optional local persisted-state metadata. No API calls.
"""
from pathlib import Path
import ast,hashlib,os
R=Path("/opt/render/project/src")
def segment(lines,needle,start=0):
 for i in range(start,len(lines)):
  if needle in lines[i]:return i+1
 return None
def main():
 print("F15 EARLY HANDOFF | A COVERAGE AND TIMING AUDIT V1")
 print("READ ONLY | NO NETWORK | NO PRODUCTION WRITE | NO A/B IMPORT")
 p=R/"fugle_a_scanner_v2_4.py"
 if not p.exists():raise SystemExit("AUDIT STOP: A source missing")
 src=p.read_text(encoding="utf-8-sig");lines=src.splitlines();ast.parse(src)
 print("A_SHA256",hashlib.sha256(p.read_bytes()).hexdigest())
 def where(label,phrase):
  xs=[i for i,s in enumerate(lines,1) if phrase in s]
  print("LOC",label,xs[:20])
  return xs
 where("SNAPSHOT","self.adapter.snapshot()")
 where("MOTHER_FILTER","candidates = [")
 where("MOTHER_IDENTITY","record_a_scan_mother_identity(snap_date, symbol)")
 where("HISTORY_READY","daily_history_local_ready(symbol, snap_date)")
 where("ESTIMATION","self.adapter.estimated_vr5_parts(")
 where("ARMED_BRANCH","if not armed:")
 where("ARMED_INFO","self.armed_info(snap_date, symbol)")
 where("FORMAL_HANDOFF","self.handoff_hit(hit, snap_date)")
 where("QUEUE_COMPARE","QUEUE_COMPARE")
 where("DATA_TIMESTAMP","source_data_time")
 where("OBSERVED_AT","observed_at")
 print("KEY_BRANCH_EXCERPTS")
 for a,b in [(1538,1551),(1562,1595),(1655,1695),(1725,1755)]:
  print("LINES",a,b)
  for i in range(a,min(b,len(lines))+1):
   s=lines[i-1]
   if any(t in s.lower() for t in ("token","secret","password","api_key","authorization","bearer")):s="[REDACTED]"
   print(f"{i:04d} {s[:170]}")
 print("INTERPRETATION")
 print("1. A mother filter occurs BEFORE estimator; full-market coverage is not proven.")
 print("2. WAIT_DATA defers candidates; first market eligibility and actual processing can differ.")
 print("3. Estimator is guarded by if-not-armed; already-armed candidates may lack fresh EVG.")
 print("4. Market-minute timestamp and receipt timestamp must be verified from snapshot source.")
 print("5. Static inspection cannot prove which events were observed live or quantify missingness.")
 print("AUDIT COMPLETE | NO MUTATIONS")
if __name__=="__main__":main()
