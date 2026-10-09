#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline schedule/coverage gate tests; no network and no production writes."""
import datetime as dt
import importlib.util
import sqlite3
import tempfile
from pathlib import Path

src=Path("/tmp/a_daily_incremental_maintenance_v1.py")
if not src.is_file():
    raise SystemExit("STOP: download staging maintenance script to /tmp first")
spec=importlib.util.spec_from_file_location("daily_maint",src)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
tz=dt.timezone(dt.timedelta(hours=8))
with tempfile.TemporaryDirectory(prefix="a_daily_maint_test_") as tmp:
    root=Path(tmp); f10=root/"f10.sqlite3";daily=root/"daily.sqlite3"
    with sqlite3.connect(f10) as db:
        db.execute("CREATE TABLE member(symbol TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO member VALUES(?)",[("1303",),("2330",),("3714",)])
    with sqlite3.connect(daily) as db:
        db.execute("CREATE TABLE fetch_status(symbol TEXT PRIMARY KEY,covered_through TEXT)")
        db.executemany("INSERT INTO fetch_status VALUES(?,?)",[
            ("1303","2026-10-09"),("2330","2026-10-08"),("3714","2026-10-09")])
    before=dt.datetime(2026,10,9,14,29,tzinfo=tz)
    try:m.plan(before,daily,f10)
    except ValueError as e:assert "post-close" in str(e)
    else:raise AssertionError("pre-close allowed")
    print("PASS 14:29 blocked")
    after=dt.datetime(2026,10,9,14,30,tzinfo=tz)
    p=m.plan(after,daily,f10)
    assert p["due"]==1 and p["already_covered"]==2 and p["asof"]=="2026-10-10",p
    print("PASS 14:30 incremental due=1, covered=2")
    # Simulate successful fetch_status advancement, without running Fugle.
    with sqlite3.connect(daily) as db:
        db.execute("UPDATE fetch_status SET covered_through=? WHERE symbol=?",("2026-10-09","2330"))
    p=m.plan(after,daily,f10)
    assert p["due"]==0 and p["already_covered"]==3,p
    print("PASS retry after successful update due=0 (no duplicate fetch)")
    with sqlite3.connect(daily) as db:
        db.execute("DELETE FROM fetch_status WHERE symbol=?",("3714",))
    try:m.plan(after,daily,f10)
    except ValueError as e:assert "identity mismatch" in str(e)
    else:raise AssertionError("missing coverage accepted")
    print("PASS missing symbol coverage blocked")
print("RESULT = PASS | isolated temp SQLite only | NO HTTP/Bridge/LINE/production writes")
