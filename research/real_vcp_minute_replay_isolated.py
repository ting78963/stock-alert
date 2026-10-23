#!/usr/bin/env python3
"""Offline, isolated, stateful VCP replay of selected real 1m trajectories.

Requires the candidate branch's pinned VCP adapter and a local read-only copy
of Render's daily-history database. Does not import the production scanner.
Does not access network, Bridge, LINE or production state.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from vcp_scan_once_adapter import VcpScanOnceRuntime

TZ = ZoneInfo("Asia/Taipei")


def replay_one(obj, conn):
    ident = obj["identity"]
    symbol, day = str(ident["stock_id"]), str(ident["date"])
    history = conn.execute(
        "SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60",
        (symbol, day),
    ).fetchall()
    if len(history) != 60:
        return {"date": day, "stock_id": symbol, "name": ident.get("stock_name"), "status": "UNKNOWN_DAILY_60"}
    history.reverse()
    bars = [SimpleNamespace(date=str(d), close=float(c), volume_zhang=float(v)) for d, c, v in history]
    avg5 = sum(b.volume_zhang for b in bars[-5:]) / 5
    if avg5 <= 0:
        return {"date": day, "stock_id": symbol, "name": ident.get("stock_name"), "status": "UNKNOWN_PRIOR5"}
    clock = [dt.datetime.fromisoformat(day + "T09:00:00").replace(tzinfo=TZ)]
    runtime = VcpScanOnceRuntime(lambda: clock[0])
    hits = []
    count = 0
    for minute in sorted(obj.get("trajectory_raw_1m") or [], key=lambda x: str(x.get("minute") or "")):
        time = str(minute.get("minute") or "")
        try:
            hhmm = time[-5:] if len(time) >= 5 else time
            hh, mm = map(int, hhmm.split(":")[:2])
            clock[0] = dt.datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=TZ)
            volume = float(minute["cum_volume"])
            close = float(minute["close"])
        except (ValueError, TypeError, KeyError):
            continue
        if volume < 800 and not (runtime.has_pending(day, symbol) or runtime.has_watch(day, symbol) or runtime.has_active_track(symbol)):
            continue
        row = {"stock_id": symbol, "date": day, "name": ident.get("stock_name") or symbol,
               "total_volume": volume, "close": close, "change_rate": float(minute.get("close_gain_pct") or 0)}
        result = runtime.evaluate(row, bars, {}, volume / avg5, 4)
        count += 1
        for proposal in result.get("proposals") or []:
            hits.append({"minute": time, "source": proposal.get("source"), "proposal": proposal})
            break  # report first handoff; preserve runtime state
        if hits:
            break
    return {"date": day, "stock_id": symbol, "name": ident.get("stock_name"),
            "status": "HIT" if hits else ("NO_HIT" if count else "NO_ELIGIBLE_MINUTES"),
            "evaluated_minutes": count, "first_hit": hits[0] if hits else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/var/data/stock-alert")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    root = pathlib.Path(args.root)
    conn = sqlite3.connect(f"file:{root / 'shared_history_stage_v1.sqlite3'}?mode=ro", uri=True)
    files = sorted(p for p in (root / "f15_eod/trajectory_v1").glob("*/*.json") if p.name != "manifest.json")
    if args.limit:
        files = files[:args.limit]
    counts = collections.Counter()
    for path in files:
        try:
            result = replay_one(json.loads(path.read_text(encoding="utf-8")), conn)
        except Exception as exc:
            result = {"file": str(path), "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        counts[result["status"]] += 1
        if result["status"] in ("HIT", "ERROR"):
            print(json.dumps(result, ensure_ascii=False, default=str))
    print("SUMMARY", json.dumps(dict(sorted(counts.items())), ensure_ascii=False))
    print("LIMITATION: signal-selected trajectories, not a whole-market replay; minute bar time is not verified snapshot receipt time")
    conn.close()


if __name__ == "__main__":
    main()
