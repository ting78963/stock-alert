#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only source schema audit for shared-history phase 1. No network, no writes."""
import json, sqlite3
from collections import Counter
from pathlib import Path

ROOT=Path("/var/data/stock-alert")
F10=ROOT/"f10_baseline_v1.sqlite3"
BACKUP=ROOT/"a_cache_backup_20261001/a_history_cache_v2_4.json"
STAGE=ROOT/"_f10_expansion_research/f10_expansion_stage_v1.sqlite3"

def sqlite_audit(path):
    if not path.exists():
        return {"exists":False}
    con=sqlite3.connect(f"file:{path}?mode=ro",uri=True)
    try:
        tables=[x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        out=[]
        for table in tables:
            safe='"'+table.replace('"','""')+'"'
            columns=[{"name":r[1],"type":r[2]} for r in con.execute(f"PRAGMA table_info({safe})")]
            count=con.execute(f"SELECT COUNT(*) FROM {safe}").fetchone()[0]
            out.append({"table":table,"columns":columns,"rows":count})
        return {"exists":True,"bytes":path.stat().st_size,"tables":out,"integrity":con.execute("PRAGMA quick_check").fetchone()[0]}
    finally:
        con.close()

def json_audit(path):
    if not path.exists():
        return {"exists":False}
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):
        return {"exists":True,"type":type(obj).__name__,"STOP":"unexpected JSON root"}
    counts=Counter(k.split("|",1)[0] for k in obj)
    examples={}
    for k,v in obj.items():
        prefix=k.split("|",1)[0]
        if prefix not in examples:
            examples[prefix]={"key":k,"value_type":type(v).__name__,"length":len(v) if isinstance(v,(dict,list)) else None}
            if isinstance(v,list) and v and isinstance(v[0],dict):
                examples[prefix]["first_row_fields"]=list(v[0])
    return {"exists":True,"bytes":path.stat().st_size,"key_prefix_counts":dict(counts),"examples":examples}

def main():
    print(json.dumps({"mode":"READ_ONLY","f10":sqlite_audit(F10),"f10_expansion":sqlite_audit(STAGE),"a_backup":json_audit(BACKUP)},ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
