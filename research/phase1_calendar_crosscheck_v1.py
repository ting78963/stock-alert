#!/usr/bin/env python3
"""READ ONLY: cross-check staged OHLCV dates against two anchors and F10 observed dates.
This is NOT an official exchange calendar and does NOT certify historical completeness.
"""
import sqlite3, json, sys
from pathlib import Path
H=Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
F=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
def ro(p):
    if not p.is_file(): raise RuntimeError("missing "+str(p))
    return sqlite3.connect(p.resolve().as_uri()+"?mode=ro",uri=True)
def main():
    h=ro(H);f=ro(F)
    try:
        if h.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("history integrity failed")
        a={r[0] for r in h.execute("SELECT day FROM daily_ohlcv WHERE symbol='1101'")}
        b={r[0] for r in h.execute("SELECT day FROM daily_ohlcv WHERE symbol='1301'")}
        obs={r[0] for r in f.execute("SELECT DISTINCT day FROM f10_day")}
        if not a or not b or a!=b:raise RuntimeError("anchor dates missing or disagree")
        if not obs.issubset(a):raise RuntimeError("F10 observed dates absent from anchor: "+str(sorted(obs-a)))
        rows=h.execute("SELECT symbol,COUNT(*),MIN(day),MAX(day) FROM daily_ohlcv GROUP BY symbol ORDER BY symbol").fetchall()
        issues=[]
        for symbol,n,first,last in rows:
            dates={r[0] for r in h.execute("SELECT day FROM daily_ohlcv WHERE symbol=?",(symbol,))}
            missing=sorted(a-dates)
            extra=sorted(dates-a)
            if missing or extra:issues.append({"symbol":symbol,"missing":missing[:15],"extra":extra[:15],"missing_count":len(missing),"extra_count":len(extra)})
        result={"status":"PASS_INTERNAL_ONLY" if not issues else "STOP_MISMATCH","anchor_sessions":len(a),"anchor_first":min(a),"anchor_last":max(a),"f10_observed_days":len(obs),"symbols_checked":len(rows),"issues_count":len(issues),"issues":issues[:20],"official_calendar_certified":False,"writes":False}
        print(json.dumps(result,ensure_ascii=False))
        if issues:sys.exit(2)
    finally:h.close();f.close()
if __name__=="__main__":
    try:main()
    except Exception as e:print("STOP:",e);sys.exit(2)
