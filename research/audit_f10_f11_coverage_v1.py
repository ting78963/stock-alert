#!/usr/bin/env python3
"""Read-only F10/F11 coverage audit. Never changes production data or calls Fugle."""
import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_ROOT = Path("/var/data/stock-alert")
EXCLUDED = {"02", "09", "14", "15", "16", "17", "18", "22", "32"}

def f10_symbols(path):
    if not path.is_file():
        return None
    with sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True) as db:
        return {str(row[0]) for row in db.execute("SELECT DISTINCT symbol FROM f10_day")}

def f11_records(path):
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw.get("symbols") if isinstance(raw, dict) else None
    if not isinstance(records, dict):
        raise ValueError("F11 symbols map missing")
    return records

def snapshot_symbols(path):
    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("data", raw.get("rows"))
    if not isinstance(raw, list):
        raise ValueError("snapshot must be a JSON array or data/rows array")
    return {str(x.get("stock_id") or x.get("symbol")) for x in raw
            if isinstance(x, dict) and (x.get("stock_id") or x.get("symbol"))}

def audit(f10, f11, snapshot=None):
    records = f11 or {}
    valid = {s for s, x in records.items() if isinstance(x, dict)
             and str(x.get("symbol") or "") == s
             and x.get("market") in ("TSE", "OTC")
             and str(x.get("securityType") or "") == "01"
             and str(x.get("industry") or "").strip()}
    eligible = {s for s in valid if str(records[s]["industry"]) not in EXCLUDED}
    invalid = set(records) - valid
    universe = snapshot if snapshot is not None else f10
    result = {
        "f10_symbols": None if f10 is None else len(f10),
        "f11_cached": None if f11 is None else len(records),
        "f11_valid": len(valid),
        "f11_eligible_by_existing_rules": len(eligible),
        "f11_invalid_or_incomplete": len(invalid),
        "snapshot_symbols": None if snapshot is None else len(snapshot),
        "comparison_universe": "snapshot" if snapshot is not None else ("f10_proxy_only" if f10 is not None else "none"),
        "universe_missing_f11": None if universe is None else len(universe - set(records)),
        "universe_missing_valid_f11": None if universe is None else len(universe - valid),
        "f10_missing_f11": None if f10 is None else len(f10 - set(records)),
        "f11_not_in_f10": None if f10 is None else len(set(records) - f10),
        "missing_valid_symbols": None if universe is None else sorted(universe - valid),
        "invalid_symbols": sorted(invalid),
    }
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--snapshot-json", type=Path)
    p.add_argument("--output", type=Path, help="optional report file; default stdout only")
    args = p.parse_args()
    f10 = f10_symbols(args.root / "f10_baseline_v1.sqlite3")
    f11 = f11_records(args.root / "a_f11_metadata_v1.json")
    report = audit(f10, f11, snapshot_symbols(args.snapshot_json))
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
