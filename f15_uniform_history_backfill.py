# -*- coding: utf-8 -*-
"""One-time F15 history resend using the single current renderer.
Reads canonical F15 archives only: no market refetch, no recognition recompute.
"""
import json, os, time, urllib.request, urllib.error, uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import f15_eod_signal_report as f15

TPE=ZoneInfo("Asia/Taipei")
DATES=("2026-09-29","2026-09-30","2026-10-01","2026-10-02","2026-10-05")
REG=f15.OUT/"uniform_history_v2_registry.json"

def atomic(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_suffix(p.suffix+".tmp")
    q.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
    q.replace(p)

def load_reg():
    if not REG.exists(): return {"schema":"f15_uniform_history_v2","dates":{}}
    x=json.loads(REG.read_text(encoding="utf-8"))
    if x.get("schema")!="f15_uniform_history_v2": raise RuntimeError("F15 uniform registry schema mismatch")
    return x

def send_uniform(report):
    token,to=f15.creds()
    payload={"to":to,"messages":[f15.flex(report)],"notificationDisabled":False}
    data=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"f15-uniform-history-v2:"+report["date"]))
    req=urllib.request.Request(f15.ENDPOINT,data=data,method="POST",headers={"Content-Type":"application/json","Authorization":"Bearer "+token,"X-Line-Retry-Key":retry})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            status=r.status; body=r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"F15 UNIFORM LINE HTTP {e.code}: "+e.read().decode(errors="replace")[:800]) from e
    if status!=200: raise RuntimeError(f"F15 UNIFORM LINE status {status}: {body[:500]}")

def run():
    # Delay until production worker has completed startup/self-test.
    time.sleep(20)
    r=load_reg()
    for day in DATES:
        if day in r["dates"]: continue
        p=f15.OUT/f"{day}.json"
        if not p.is_file():
            print(f"[F15 UNIFORM WAIT] archive missing {day}",flush=True)
            return
        report=json.loads(p.read_text(encoding="utf-8"))
        if report.get("date")!=day or not isinstance(report.get("rows"),list):
            raise RuntimeError(f"F15 uniform archive identity mismatch {p}")
        send_uniform(report)
        r["dates"][day]={"sent_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),"renderer":"compact-uniform-v2","total":report.get("total")}
        atomic(REG,r)
        print(f"[F15 UNIFORM SENT] {day} total={report.get('total')}",flush=True)
        time.sleep(1)
    print("[F15 UNIFORM DONE] chronological history resend complete",flush=True)
