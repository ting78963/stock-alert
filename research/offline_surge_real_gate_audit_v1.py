#!/usr/bin/env python3
"""Historical SURGE gate audit using real scanner decision method; never sends signals.

F10 intraday fraction is NOT recoverable from daily OHLCV alone. Report UNKNOWN
instead of fabricating F10. Volume-below-1000 returns genuine gate FAIL.
"""
import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

import fugle_a_scanner_v2_4 as a

ROOT = Path("/var/data/stock-alert")
CACHE = ROOT / "_research_output/f15_174_api_800_1000_v1/api_day_cache"
DB = ROOT / "shared_history_stage_v1.sqlite3"

class OfflineAdapter:
    def has_complete_f10_cache_only(self, symbol, day):
        return False  # No historical intraday F10 profile verified: fail closed.

def run(day):
    paths = sorted(CACHE.glob(f"*_{day}.json"))
    if not paths or not DB.is_file():
        raise SystemExit("STOP: minute cache or daily database missing")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    scanner = a.Scanner.__new__(a.Scanner)
    scanner.adapter = OfflineAdapter()
    totals = Counter()
    output = []
    for path in paths:
        symbol = path.stem.split("_", 1)[0]
        raw = json.loads(path.read_text(encoding="utf-8"))
        bars = raw.get("data", [])
        if not bars:
            totals["NO_BARS"] += 1
            continue
        prior = con.execute("SELECT volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 10", (symbol,day)).fetchall()
        if len(prior) != 10:
            totals["NO_F10_DAILY"] += 1
            continue
        cum = 0
        first_unknown = None
        for bar in sorted(bars,key=lambda x:x["date"]):
            ts = datetime.fromisoformat(bar["date"]).astimezone(ZoneInfo("Asia/Taipei"))
            if ts.date().isoformat()!=day:
                raise SystemExit(f"STOP: date mismatch {symbol}")
            vol=float(bar["volume"])
            if vol < 0: raise SystemExit(f"STOP: negative volume {symbol}")
            cum += vol
            if cum < 1000: continue
            snap={"stock_id":symbol,"date":day,"total_volume":cum}
            status,reason,metrics=scanner.snapshot_surge_decision(snap,day,ts)
            if status == "PASS":
                raise SystemExit("STOP: unexpected PASS without F10")
            first_unknown={"symbol":symbol,"first_1000":ts.strftime("%H:%M"),
                           "status":status,"reason":reason}
            break
        if first_unknown:
            totals[first_unknown["status"]] += 1
            output.append(first_unknown)
        else:
            totals["BELOW_1000"] += 1
    con.close()
    print(json.dumps({"date":day,"stocks":len(paths),"results":dict(totals),
      "scope":"cached symbols only","warning":"SURGE UNKNOWN is not a failed signal; historical F10 is unverified",
      "line_sent":False},ensure_ascii=False))
    for row in output:
        print(json.dumps(row,ensure_ascii=False))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--day",default="2026-09-21")
    run(ap.parse_args().day)
