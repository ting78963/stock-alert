#!/usr/bin/env python3
"""Read-only daily/F10 same-session volume reconciliation; no API, no writes."""
import datetime as dt, sqlite3, json
from pathlib import Path
ROOT=Path("/var/data/stock-alert")
DAILY=ROOT/"shared_history_stage_v1.sqlite3"
F10=ROOT/"f10_baseline_v1.sqlite3"
def ro(p):return sqlite3.connect(p.resolve().as_uri()+"?mode=ro",uri=True)
def main():
 if not DAILY.is_file() or not F10.is_file():raise SystemExit("STOP missing DB")
 with ro(DAILY) as d,ro(F10) as f:
  day=d.execute("SELECT MAX(day) FROM daily_ohlcv").fetchone()[0]
  if not day:raise SystemExit("STOP empty daily")
  daily={str(s):float(v) for s,v in d.execute("SELECT symbol,volume_zhang FROM daily_ohlcv WHERE day=?",(day,))}
  f10={str(s):float(v) for s,v in f.execute("SELECT symbol,full FROM f10_day WHERE day=?",(day,))}
  both=set(daily)&set(f10)
  # F10 historical minute volume is shares; daily_ohlcv volume_zhang is lots.
  ratios=[f10[s]/(daily[s]*1000) for s in both if daily[s]>0]
  print("LATEST_DAILY_DAY =",day,"DAILY_SYMBOLS =",len(daily),"F10_SYMBOLS =",len(f10),"OVERLAP =",len(both))
  print("ONLY_DAILY =",len(set(daily)-set(f10)),"ONLY_F10 =",len(set(f10)-set(daily)))
  if ratios:print("RATIO_F10_SHARES_OVER_DAILY_SHARES =",{"min":round(min(ratios),5),"median":round(sorted(ratios)[len(ratios)//2],5),"max":round(max(ratios),5)})
  print("READ_ONLY_DIAGNOSTIC | NO API | NO WRITES | NO COMPLETENESS CERTIFICATION")
if __name__=="__main__":main()
