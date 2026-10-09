#!/usr/bin/env python3
"""Offline A preflight integration tests. No network, no production writes."""
import importlib.util,sqlite3,tempfile
from datetime import date
from pathlib import Path
import twse_session_gate_v1 as gate
spec=importlib.util.spec_from_file_location("preflight","/tmp/a_history_preflight_v1.py")
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def forbidden(*a,**k):raise AssertionError("HTTP forbidden")
gate.fetch_schedule=forbidden
p.fetch_schedule=forbidden
rows=[{"Date":"1151009","Name":"國慶日補假，停止交易"},{"Date":"1151010","Name":"國慶日，停止交易"}]
db="/var/data/stock-alert/shared_history_stage_v1.sqlite3"
got=p.verify_a_history("2026-10-12",db,rows=rows)
assert got=="2026-10-08",got
print("PASS: 2026-10-12 -> 2026-10-08; shared DB verified")
try:p.verify_a_history("2026-10-12","/tmp/no_such_a_history_database.sqlite3",rows=rows)
except p.AHistoryPreflightError:print("PASS: missing DB blocks A")
else:raise AssertionError("missing DB not blocked")
with tempfile.TemporaryDirectory() as td:
    path=str(Path(td)/"incomplete.sqlite3")
    c=sqlite3.connect(path)
    c.execute("CREATE TABLE fetch_status(symbol TEXT,covered_through TEXT)")
    c.execute("CREATE TABLE daily_ohlcv(symbol TEXT)")
    c.execute("INSERT INTO fetch_status VALUES('1101','2026-10-07')")
    c.execute("INSERT INTO daily_ohlcv VALUES('1101')")
    c.commit();c.close()
    try:p.verify_a_history("2026-10-12",path,rows=rows)
    except p.AHistoryPreflightError:print("PASS: incomplete watermark blocks A")
    else:raise AssertionError("stale watermark not blocked")
try:p.verify_a_history("2026-10-12",db,rows=[])
except p.AHistoryPreflightError:print("PASS: invalid calendar blocks A")
else:raise AssertionError("invalid calendar not blocked")
print("HTTP = BLOCKED; PRODUCTION WRITES = NONE")
print("NOTE: test does not launch A/B/LINE or exercise worker loop")
