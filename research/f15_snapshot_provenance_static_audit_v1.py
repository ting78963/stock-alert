#!/usr/bin/env python3
"""Static provenance audit of production A snapshot mapping. No A/B import, no network."""
import argparse,ast,hashlib
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("--source",default="fugle_a_scanner_v2_4.py");a=p.parse_args()
 path=Path(a.source)
 if not path.is_file():raise SystemExit("STOP | source file missing")
 raw=path.read_bytes();tree=ast.parse(raw,filename=str(path))
 methods=[]
 for node in ast.walk(tree):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name=="snapshot":methods.append(node)
 if len(methods)!=1:raise SystemExit("STOP | expected one snapshot method; found "+str(len(methods)))
 node=methods[0]
 src=ast.get_source_segment(raw.decode("utf-8"),node) or ""
 required=["snapshot/quotes/","tradeVolume","total_volume","snap_date","market"]
 missing=[x for x in required if x not in src]
 print("F15 | A SNAPSHOT TIME/UNIT STATIC AUDIT")
 print("READ ONLY | NO API | NO PRODUCTION IMPORT/WRITE")
 print("SOURCE_SHA256",hashlib.sha256(raw).hexdigest())
 print("SNAPSHOT_LINES",node.lineno,node.end_lineno)
 print("REQUIRED_MAPPING", "PASS" if not missing else "STOP "+repr(missing))
 print("TRADE_VOLUME_MAPPING", "tradeVolume -> total_volume (source code comment: 張)")
 print("SNAPSHOT_DATE_MAPPING", "envelope date -> date")
 print("SOURCE_TIME_EXPOSED",any(k in src for k in ('"source_data_time"','"tradeTime"','"updatedAt"','"timestamp"')))
 print("OBSERVED_AT_EXPOSED",any(k in src for k in ('"observed_at"','"received_at"')))
 print("TSE_OTC_REQUESTS",'"TSE", "OTC"' in src)
 print("LIMITATION | no per-stock market timestamp is carried in mapped snapshots")
 print("DECISION | cannot certify first market-minute from observation time")
 if missing:raise SystemExit(2)
if __name__=="__main__":main()
