#!/usr/bin/env python3
"""Read-only, fail-closed gate for a future external restart supervisor.

This command does NOT restart anything or send LINE. It validates a shared,
explicitly supplied maintenance status snapshot; the worker's /var/data is not
accessible to GitHub Actions. Exit 0=eligible, 1=not eligible, 2=invalid input.
"""
import argparse
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

TPE = ZoneInfo("Asia/Taipei")
REQUIRED = {"DAILY_K", "F10"}

def check(state, now):
    if not isinstance(state, dict):
        return False, "invalid state"
    day = now.date().isoformat()
    if state.get("schema") != "daily_maintenance_state_v2" or state.get("date") != day:
        return False, "maintenance state missing, stale, or incompatible"
    stages = state.get("stages")
    if not isinstance(stages, list) or any(not isinstance(x, str) for x in stages):
        return False, "invalid maintenance stage list"
    if not REQUIRED.issubset(set(stages)):
        return False, "DAILY_K/F10 not complete"
    if state.get("line_sent") is not True:
        return False, "maintenance LINE not accepted"
    accepted = state.get("line_accepted_at")
    try:
        when = dt.datetime.fromisoformat(accepted)
        if when.tzinfo is None:
            return False, "LINE timestamp lacks timezone"
        when = when.astimezone(TPE)
    except (TypeError, ValueError):
        return False, "missing/invalid LINE accepted timestamp"
    if when.date() != now.date() or not dt.timedelta(hours=2) <= now - when < dt.timedelta(hours=24):
        return False, "two-hour wait not satisfied"
    if state.get("f15_complete") is not True:
        return False, "F15 end-of-day not confirmed"
    if type(state.get("active_trading_jobs")) is not int or state["active_trading_jobs"] != 0:
        return False, "active trading jobs not confirmed idle"
    if state.get("disk_ok") is not True or state.get("database_ok") is not True:
        return False, "disk/database health not confirmed"
    if state.get("restart_attempted") is not False:
        return False, "daily restart already attempted or unknown"
    return True, "preflight eligible (no restart performed)"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state-file", required=True)
    p.add_argument("--now", help="ISO 8601 timestamp; defaults to current Taiwan time")
    args = p.parse_args()
    try:
        now = dt.datetime.fromisoformat(args.now).astimezone(TPE) if args.now else dt.datetime.now(TPE)
        with open(args.state_file, encoding="utf-8") as f:
            state = json.load(f)
        ok, reason = check(state, now)
    except (OSError, ValueError, TypeError) as exc:
        print(f"INVALID: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(("ELIGIBLE" if ok else "SKIP") + ": " + reason)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
