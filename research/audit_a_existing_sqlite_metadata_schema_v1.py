#!/usr/bin/env python3
"""Read-only SQLite schema inventory for reusable A metadata."""
import sqlite3
from pathlib import Path
paths=[Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3"),Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")]
for path in paths:
    print("DATABASE =",path.name)
    if not path.is_file():
        print("MISSING; SKIP");continue
    db=sqlite3.connect(f"file:{path}?mode=ro",uri=True)
    try:
        tables=db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name").fetchall()
        for (name,) in tables:
            if name.startswith("sqlite_"):continue
            cols=[r[1] for r in db.execute("PRAGMA table_info("+chr(34)+name.replace(chr(34),chr(34)*2)+chr(34)+")")]
            print("TABLE =",name,"COLUMNS =",",".join(cols))
    finally:db.close()
print("GOAL: locate authoritative market/securityType/industry fields, not infer them from price or stock ID")
print("READ_ONLY=YES; HTTP=NONE; A/B/LINE=NONE; PRODUCTION_WRITES=NONE")
