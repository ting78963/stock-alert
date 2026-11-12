#!/usr/bin/env python3
"""Read-only VCP input audit. No network calls and no production writes."""
import argparse
import collections
import json
import sqlite3
from pathlib import Path

ROOT = Path("/var/data/stock-alert")
EXCLUDED = {"02", "09", "14", "15", "16", "17", "18", "22", "32"}

def load_cache(path):
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj.get("symbols", {}) if isinstance(obj.get("symbols"), dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}

def classify(meta):
    if not isinstance(meta, dict):
        return "MISSING_F11"
    if str(meta.get("market", "")).upper() == "ESB":
        return "EXCLUDED_ESB"
    if str(meta.get("securityType", "")) != "01":
        return "EXCLUDED_SECURITY_TYPE"
    if str(meta.get("industry", "")).zfill(2) in EXCLUDED:
        return "EXCLUDED_INDUSTRY"
    return "ELIGIBLE_F11"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", default=["2026-11-11", "2026-11-12"])
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()
    events = args.root / "a_scanner_v2/events.jsonl"
    cache = load_cache(args.root / "a_f11_metadata_v1.json")
    unknown = {}
    types = collections.Counter()
    with events.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            day = str(e.get("date") or e.get("day") or "")
            if day not in args.days:
                continue
            typ = str(e.get("type") or "")
            if typ in {"vcp_fire", "layered_vcp_handoff", "vcp_unknown"}:
                types[(day, typ)] += 1
            if typ == "vcp_unknown":
                symbol = str(e.get("symbol") or "")
                if symbol:
                    unknown[(day, symbol, str(e.get("reason") or ""))] = True
    categories = collections.Counter()
    missing = set()
    short = set()
    for day, symbol, reason in unknown:
        if reason == "VCP_METADATA_NOT_READY":
            category = classify(cache.get(symbol))
            categories[(day, category)] += 1
            if category == "MISSING_F11":
                missing.add(symbol)
        elif reason == "VCP_PRIOR_60_DAILY_BARS_NOT_READY":
            short.add(symbol)
            categories[(day, "SHORT_HISTORY")] += 1
        else:
            categories[(day, reason)] += 1
    print("EVENT_COUNTS", dict(sorted((f"{d}/{t}", n) for (d,t),n in types.items())))
    print("UNKNOWN_BREAKDOWN", dict(sorted((f"{d}/{t}", n) for (d,t),n in categories.items())))
    print("F11_CACHE_STOCKS", len(cache))
    print("MISSING_F11_SYMBOLS", sorted(missing))
    print("SHORT_HISTORY_SYMBOLS", sorted(short))
    db = args.root / "shared_history_stage_v1.sqlite3"
    if not db.is_file():
        print("HISTORY_DB_NOT_FOUND", db)
        return
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as conn:
        for symbol in sorted(missing | short):
            try:
                row = conn.execute("SELECT COUNT(*),MIN(day),MAX(day) FROM daily_ohlcv WHERE symbol=?", (symbol,)).fetchone()
                print("HISTORY", symbol, "count", row[0], "first", row[1], "last", row[2],
                      "f11", classify(cache.get(symbol)))
            except sqlite3.Error as exc:
                print("HISTORY_QUERY_ERROR", type(exc).__name__, str(exc))
                break

if __name__ == "__main__":
    main()
