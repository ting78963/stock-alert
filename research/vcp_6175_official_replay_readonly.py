#!/usr/bin/env python3
"""Isolated official VCP replay; never import scanner or write production files."""
import ast
import json
import math
import sqlite3
from pathlib import Path

SRC = Path("/opt/render/project/src/fugle_a_scanner_v2_4.py")
DB = Path("/var/data/stock-alert/shared_history_stage_v1.sqlite3")
MIN = Path("/var/data/stock-alert/b_live_runner_v2_p1/2026-10-01/6175/canonical_minutes.jsonl")
DAY, SID = "2026-10-01", "6175"
LIMITS = (0, 500, 800, 1000, 2000)

def main():
    print("VCP 6175 | OFFICIAL FUNCTION | READ ONLY | NO API | NO PRODUCTION WRITE")
    for p in (SRC, DB, MIN):
        if not p.is_file():
            raise RuntimeError("STOP_MISSING_FILE: " + str(p))
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "StrongSelector"]
    if len(classes) != 1:
        raise RuntimeError("STOP_SELECTOR_IDENTITY")
    helpers = {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("sd_of", "safe_max")}
    methods = [n for n in classes[0].body if isinstance(n, ast.FunctionDef) and n.name == "analyze_vcp"]
    if set(helpers) != {"sd_of","safe_max"} or len(methods) != 1:
        raise RuntimeError("STOP_VCP_FUNCTION_IDENTITY")
    # Exact function AST only. No module import, no constructor, no production track file.
    import copy
    method = copy.deepcopy(methods[0])
    method.decorator_list = []
    ns = {"math":math,"List":list,"Dict":dict,"Any":object}
    mod = ast.Module(body=[copy.deepcopy(helpers["sd_of"]),copy.deepcopy(helpers["safe_max"]),method],type_ignores=[])
    ast.fix_missing_locations(mod)
    exec(compile(mod,str(SRC),"exec"),ns)
    class Isolated:
        track_path = None
        def __init__(self):
            self.track = {}
    Isolated.analyze_vcp = ns["analyze_vcp"]
    selector = Isolated()
    with sqlite3.connect(f"file:{DB}?mode=ro",uri=True) as con:
        hist = con.execute("SELECT day,close,volume_zhang FROM daily_ohlcv WHERE symbol=? AND day<? ORDER BY day DESC LIMIT 65",(SID,DAY)).fetchall()
    hist.reverse()
    if len(hist)<60 or len({x[0] for x in hist})!=len(hist) or any(x[0]>=DAY or x[1] is None or float(x[1])<=0 or x[2] is None or float(x[2])<0 for x in hist):
        raise RuntimeError("STOP_HISTORY_COVERAGE_OR_IDENTITY")
    rows = [json.loads(s) for s in MIN.read_text(encoding="utf-8").splitlines() if s.strip()]
    times = [r["minute"] for r in rows]
    if not rows or times!=sorted(set(times)) or any(r.get("date")!=DAY or str(r.get("stock_id"))!=SID or float(r["volume"])<0 or float(r["close"])<=0 for r in rows):
        raise RuntimeError("STOP_MINUTE_COVERAGE_OR_IDENTITY")
    dates=[x[0] for x in hist]; closes=[float(x[1]) for x in hist]; vols=[float(x[2]) for x in hist]
    first={}; cum=0.; new_count=0
    for r in rows:
        cum+=float(r["volume"])
        result=selector.analyze_vcp(closes+[float(r["close"])],vols+[cum],SID,dates+[DAY])
        track=result.get("breakoutTrack") or {}
        is_new=track.get("isNew") is True and track.get("dayCount")==1 and not track.get("broken")
        if is_new:
            new_count+=1
            first.setdefault("NEW", (r["minute"],round(cum,2),result["status"]))
        active=track.get("dayCount")==1 and not track.get("broken")
        for t in LIMITS:
            if active and cum>=t:
                first.setdefault(str(t),(r["minute"],round(cum,2),result["status"]))
    print("HISTORY:",len(hist),"MINUTES:",len(rows),"NEW_EVENTS:",new_count)
    for key in ("NEW", "0", "500", "800", "1000", "2000"):
        print(key,first.get(key,"NOT_REACHED"))
    print("NOTE: first active breakoutTrack, not necessarily fresh breakout at threshold crossing")
    print("STATUS: PASS_RESEARCH_REPLAY")

if __name__=="__main__":
    main()
