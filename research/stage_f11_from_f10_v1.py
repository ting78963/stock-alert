#!/usr/bin/env python3
"""Build F10-aligned F11 staging without modifying production."""
import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/var/data/stock-alert")
BASE = "https://api.fugle.tw/marketdata/v1.0/stock"

def load_f10(path):
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        return {str(r[0]) for r in db.execute("SELECT DISTINCT symbol FROM f10_day")}

def valid(symbol, value):
    return (isinstance(value, dict)
            and str(value.get("symbol") or "") == symbol
            and str(value.get("market") or "") in ("TSE", "OTC", "TIB")
            and str(value.get("securityType") or "") in ("01", "19")
            and bool(str(value.get("industry") or "").strip()))

def fetch(symbol, key, timeout):
    url = BASE + "/intraday/ticker/" + urllib.parse.quote(symbol)
    req = urllib.request.Request(url, headers={"X-API-KEY": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--staging", type=Path, default=None)
    ap.add_argument("--api-key-env", default="FUGLE_API_KEY")
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--timeout", type=float, default=12)
    ap.add_argument("--fetch", action="store_true", help="allow network requests and write isolated staging")
    ap.add_argument("--prepare", action="store_true", help="write exact F10-aligned staging from existing metadata, without network")
    args = ap.parse_args()
    import os
    if args.fetch and args.prepare:
        ap.error("use either --fetch or --prepare")
    staging_path = args.staging or (args.root / "f11-staging" / "a_f11_staging_v1.json")
    target = load_f10(args.root / "f10_baseline_v1.sqlite3")
    original = json.loads((args.root / "a_f11_metadata_v1.json").read_text(encoding="utf-8"))["symbols"]
    if not isinstance(original, dict):
        raise ValueError("F11 symbols must be a mapping")
    staged = {}
    if staging_path.exists():
        staged = json.loads(staging_path.read_text(encoding="utf-8")).get("symbols", {})
        if not isinstance(staged, dict):
            raise ValueError("Invalid staging symbols")
    combined = {s: v for s in sorted(target)
                for v in [staged.get(s) if valid(s, staged.get(s)) else original.get(s)]
                if valid(s, v)}
    missing = sorted(target - set(combined))
    print(json.dumps({"f10": len(target), "f11_original": len(original),
                      "staging_valid": len(combined), "remaining": len(missing),
                      "original_extras": len(set(original) - target),
                      "network_enabled": args.fetch}, ensure_ascii=False), flush=True)
    if args.prepare:
        if missing:
            raise SystemExit("Not preparing incomplete F11 staging")
        atomic_json(staging_path.with_name("a_f11_f10_aligned_v1.json"), {"symbols": combined})
        print("PREPARED exact F10-aligned staging; production unchanged", flush=True)
        return
    if not args.fetch:
        return
    key = os.environ.get(args.api_key_env)
    if not key:
        raise SystemExit("Fugle key environment variable unavailable")
    completed = 0
    for symbol in missing:
        if completed >= args.batch:
            break
        try:
            value = fetch(symbol, key, args.timeout)
            if not valid(symbol, value):
                print(f"INVALID_METADATA {symbol}", flush=True)
                continue
            combined[symbol] = value
            completed += 1
            atomic_json(staging_path.with_name("a_f11_f10_aligned_v1.json"), {"symbols": combined})
            print(f"STAGED {symbol} {len(combined)}/{len(target)}", flush=True)
        except urllib.error.HTTPError as e:
            print(f"HTTP_ERROR {symbol} status={e.code}; stop batch", flush=True)
            break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            print(f"FETCH_ERROR {symbol} {type(e).__name__}; stop batch", flush=True)
            break
        time.sleep(max(0.0, args.delay))
    print(f"BATCH_DONE fetched={completed} remaining={len(target - set(combined))}", flush=True)

if __name__ == "__main__":
    main()
