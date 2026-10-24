#!/usr/bin/env python3
"""Read-only historical minute-bar eligibility audit; NOT a VCP/SURGE/FLOW signal replay."""
import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path("/var/data/stock-alert")
CACHE = ROOT / "_research_output/f15_174_api_800_1000_v1/api_day_cache"
DB = ROOT / "shared_history_stage_v1.sqlite3"

def run(day: str) -> None:
    files = sorted(CACHE.glob(f"*_{day}.json"))
    if not files:
        raise SystemExit(f"STOP: no cached minute bars for {day}")
    if not DB.is_file():
        raise SystemExit("STOP: shared daily database missing")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = []
    problems = Counter()
    for path in files:
        symbol = path.name.split("_", 1)[0]
        raw = json.loads(path.read_text(encoding="utf-8"))
        bars = raw.get("data")
        if not isinstance(bars, list) or not bars:
            problems["missing_bars"] += 1
            continue
        daily = con.execute(
            "SELECT day,volume_zhang,close FROM daily_ohlcv "
            "WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60", (symbol, day)
        ).fetchall()
        if len(daily) < 60 or any(v is None or float(v) < 0 for _, v, _ in daily[:5]):
            problems["insufficient_daily"] += 1
            continue
        avg5 = sum(float(v) for _, v, _ in daily[:5]) / 5
        if avg5 <= 0:
            problems["invalid_avg5"] += 1
            continue
        cum = 0.0
        first800 = first1000 = None
        for bar in sorted(bars, key=lambda b: b["date"]):
            ts = datetime.fromisoformat(bar["date"])
            if ts.date().isoformat() != day:
                raise ValueError(f"{symbol}: minute date mismatch")
            vol = float(bar["volume"])
            if vol < 0:
                raise ValueError(f"{symbol}: negative minute volume")
            cum += vol
            minute = ts.strftime("%H:%M")
            if first800 is None and cum >= 800:
                first800 = minute
            if first1000 is None and cum >= 1000:
                first1000 = minute
        rows.append({"symbol":symbol, "minute_bars":len(bars), "first_800":first800,
                     "first_1000":first1000, "final_volume_zhang":round(cum,2),
                     "final_raw_vr5":round(cum/avg5,4)})
    con.close()
    print(json.dumps({"date":day,"scope":"cached stocks only; not full-market",
                      "status":"volume thresholds only; NOT actual VCP/SURGE/FLOW signals",
                      "cache_files":len(files),"audited":len(rows),
                      "first_800_count":sum(r["first_800"] is not None for r in rows),
                      "first_1000_count":sum(r["first_1000"] is not None for r in rows),
                      "excluded":dict(problems)},ensure_ascii=False))
    print("symbol,minute_bars,first_800,first_1000,final_volume_zhang,final_raw_vr5")
    for r in rows:
        print(",".join(str(r[k]) if r[k] is not None else "" for k in
                       ("symbol","minute_bars","first_800","first_1000","final_volume_zhang","final_raw_vr5")))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default="2026-09-21")
    args = parser.parse_args()
    run(args.day)
