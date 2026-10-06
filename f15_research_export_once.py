# -*- coding: utf-8 -*-
from __future__ import annotations
import base64,gzip,hashlib,json
import f15_trajectory_store as ts

DAYS=("2026-09-29","2026-09-30","2026-10-01","2026-10-02","2026-10-05","2026-10-06")
MARK=ts.OUT/"_research_export_20260929_20261006_v1.done"
CHUNK=18000

def mi(s):
    h,m=map(int,str(s)[:5].split(":")); return h*60+m

def run():
    if MARK.exists():
        print("[F15 RESEARCH EXPORT] already_done",flush=True); return
    total=0
    for day in DAYS:
        d=ts.OUT/day
        files=sorted(p for p in d.glob("*.json") if p.name!="manifest.json") if d.exists() else []
        rows=[]
        for p in files:
            x=json.loads(p.read_text(encoding="utf-8"))
            ident=x.get("identity") or {}
            t0=ident.get("recognition_time")
            if not t0: raise RuntimeError(f"missing recognition_time {p}")
            raw=[r for r in (x.get("trajectory_raw_1m") or []) if mi(r.get("minute"))<=mi(t0)]
            rows.append({"identity":ident,"causal_anchor":x.get("causal_anchor") or {},
                         "production_event_snapshot":x.get("production_event_snapshot") or {},
                         "trajectory_raw_1m_through_t0":raw})
        raw_json=json.dumps({"schema":"f15_research_export_v1","date":day,"count":len(rows),"records":rows},
                            ensure_ascii=False,separators=(",",":"),sort_keys=True).encode("utf-8")
        sha=hashlib.sha256(raw_json).hexdigest()
        enc=base64.b64encode(gzip.compress(raw_json,compresslevel=9)).decode("ascii")
        parts=[enc[i:i+CHUNK] for i in range(0,len(enc),CHUNK)] or [""]
        print(f"[F15 RESEARCH EXPORT BEGIN] day={day} count={len(rows)} bytes={len(raw_json)} sha256={sha} parts={len(parts)}",flush=True)
        for i,s in enumerate(parts,1):
            print(f"[F15 RESEARCH EXPORT PART] day={day} part={i}/{len(parts)} data={s}",flush=True)
        print(f"[F15 RESEARCH EXPORT END] day={day} sha256={sha}",flush=True)
        total+=len(rows)
    MARK.write_text(json.dumps({"schema":"f15_research_export_v1_done","days":DAYS,"total":total}),encoding="utf-8")
    print(f"[F15 RESEARCH EXPORT DONE] total={total}",flush=True)

def loop_once():
    try: run()
    except BaseException as ex:
        print(f"[F15 RESEARCH EXPORT FAIL] {type(ex).__name__}: {ex}",flush=True)
