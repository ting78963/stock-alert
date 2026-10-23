#!/usr/bin/env python3
"""Read-only inventory of real F15 trajectories on Render's persistent disk.

No imports from production scanner; no Bridge, network, state writes, or LINE.
"""
import collections
import json
import pathlib
import sqlite3

ROOT = pathlib.Path("/var/data/stock-alert")
TRAJ = ROOT / "f15_eod/trajectory_v1"
DAILY = ROOT / "shared_history_stage_v1.sqlite3"
F10 = ROOT / "f10_baseline_v1.sqlite3"


def main():
    files = sorted(p for p in TRAJ.glob("*/*.json") if p.name != "manifest.json")
    daily = sqlite3.connect(f"file:{DAILY}?mode=ro", uri=True)
    f10 = sqlite3.connect(f"file:{F10}?mode=ro", uri=True)
    rows = []
    for path in files:
        obj = json.loads(path.read_text(encoding="utf-8"))
        ident = obj.get("identity") or {}
        symbol, day = str(ident.get("symbol") or ""), str(ident.get("date") or "")
        minutes = obj.get("trajectory_raw_1m") or []
        previous = daily.execute(
            "SELECT COUNT(*) FROM (SELECT day FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 60)",
            (symbol, day),
        ).fetchone()[0]
        f10_count = f10.execute(
            "SELECT COUNT(*) FROM (SELECT day FROM f10_day WHERE symbol=? AND day<? AND full>0 AND pts_json IS NOT NULL ORDER BY day DESC LIMIT 10)",
            (symbol, day),
        ).fetchone()[0]
        rows.append((day, symbol, len(minutes), previous, f10_count))
    print("TOTAL", len(rows))
    print("NONEMPTY_MINUTES", sum(n > 0 for _, _, n, _, _ in rows))
    print("DAILY_60", sum(n >= 60 for _, _, _, n, _ in rows))
    print("F10_10_ROWS_CANDIDATE_ONLY", sum(n >= 10 for _, _, _, _, n in rows))
    print("F10 count is an inventory proxy, NOT scanner eligibility or SURGE PASS")
    byday = collections.defaultdict(lambda: [0, 0, 0])
    for day, _, _, prior, f10prior in rows:
        byday[day][0] += 1
        byday[day][1] += prior >= 60
        byday[day][2] += f10prior >= 10
    print("DATE TOTAL DAILY_60 F10_10_PROXY")
    for day, counts in sorted(byday.items()):
        print(day, *counts)
    daily.close()
    f10.close()


if __name__ == "__main__":
    main()
