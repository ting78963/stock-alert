#!/usr/bin/env python3
"""READ ONLY: distinguish actual limited trading history from A DB window truncation."""
import sqlite3
from pathlib import Path
p=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
if not p.is_file():raise SystemExit("STOP: shared SQLite missing")
db=sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True)
for sym in ("1303","2323","6236","2073"):
    total=db.execute("SELECT count(*),min(day),max(day) FROM daily_ohlcv WHERE symbol=?",(sym,)).fetchone()
    recent=db.execute("SELECT count(*),min(day),max(day) FROM daily_ohlcv WHERE symbol=? AND day BETWEEN ? AND ?",(sym,"2026-04-21","2026-10-08")).fetchone()
    status=db.execute("SELECT covered_through FROM fetch_status WHERE symbol=?",(sym,)).fetchone()
    print(f"{sym} total={total[0]} range={total[1]}..{total[2]} window170={recent[0]} range={recent[1]}..{recent[2]} covered={status[0] if status else 'NONE'}")
db.close()
print("READ_ONLY = PASS")
