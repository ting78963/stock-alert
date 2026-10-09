#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Opt-in post-close incremental daily history updater (STAGING ONLY).
Default: PLAN, no network and no writes. Explicit --execute required.
Never run this against production without approval.
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT=Path("/var/data/stock-alert")
DB=ROOT/"shared_history_stage_v1.sqlite3"
F10=ROOT/"f10_baseline_v1.sqlite3"
BUILDER=Path(__file__).resolve().parent/"phase1_fugle_daily_builder_v1.py"

def plan(now, db_path=DB, f10_path=F10):
    if now.tzinfo is None:
        raise ValueError("timezone-aware Taiwan time required")
    local=now.astimezone(dt.timezone(dt.timedelta(hours=8)))
    if (local.hour,local.minute)<(14,30):
        raise ValueError("post-close maintenance only (>=14:30 Asia/Taipei)")
    if not db_path.is_file() or not f10_path.is_file():
        raise ValueError("source SQLite missing")
    def connect_ro(path):
        return sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
    with connect_ro(f10_path) as f,connect_ro(db_path) as d:
        members={str(r[0]) for r in f.execute("SELECT symbol FROM member")}
        covered={str(s):str(day) for s,day in d.execute("SELECT symbol,covered_through FROM fetch_status")}
    if not members or not members.issubset(covered):
        raise ValueError("member/coverage identity mismatch")
    through=local.date().isoformat()
    due=sorted(s for s in members if covered[s]<through)
    return {"asof":(local.date()+dt.timedelta(days=1)).isoformat(),
            "through":through,"universe":len(members),"due":len(due),
            "already_covered":len(members)-len(due),"sample":due[:8]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--execute",action="store_true",help="Explicitly permit real historical API + staging DB writes")
    p.add_argument("--db",type=Path,default=DB)
    p.add_argument("--f10",type=Path,default=F10)
    p.add_argument("--builder",type=Path,default=BUILDER)
    p.add_argument("--delay",type=float,default=1.0)
    p.add_argument("--now",help="Testing only: timezone-aware ISO timestamp; --execute forbids it")
    a=p.parse_args()
    if a.delay<1:raise SystemExit("STOP: delay must be >=1 second")
    if a.execute and a.now:raise SystemExit("STOP: --now not allowed with --execute")
    now=dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    try: info=plan(now,a.db,a.f10)
    except Exception as exc:raise SystemExit(f"STOP: {exc}")
    print(json.dumps({"mode":"EXECUTE" if a.execute else "PLAN_ONLY",**info},ensure_ascii=False),flush=True)
    if not a.execute or not info["due"]:
        print("NO NETWORK | NO DB WRITES" if not a.execute else "ALREADY COVERED; NO API",flush=True)
        return
    if a.db.resolve()!=DB.resolve() or a.f10.resolve()!=F10.resolve():
        raise SystemExit("STOP: nonstandard paths prohibited in execute mode")
    if not a.builder.is_file():raise SystemExit("STOP: daily builder missing")
    if not os.environ.get("FUGLE_API_KEY","").strip():raise SystemExit("STOP: FUGLE_API_KEY missing")
    # Linux Render single-instance nonblocking lock. Lock only protects daily writer.
    import fcntl
    lock=Path("/tmp/a_daily_incremental_maintenance_v1.lock")
    with lock.open("w") as fd:
        try:fcntl.flock(fd.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit("STOP: another daily maintenance process is running")
        cmd=[sys.executable,str(a.builder),"--asof",info["asof"],"--delay",str(a.delay),"--db",str(a.db),"--f10",str(a.f10)]
        rc=subprocess.call(cmd)
        if rc:raise SystemExit(f"STOP: daily builder incomplete rc={rc}; next run resumes")
        print("PASS: daily incremental builder finished",flush=True)

if __name__=="__main__":main()
