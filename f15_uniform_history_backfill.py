# -*- coding: utf-8 -*-
"""One-time chronological F15 resend using approved screenshot renderer v3. Reads archives only."""
import json,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import f15_eod_signal_report as f15
TPE=ZoneInfo("Asia/Taipei");DATES=("2026-09-29","2026-09-30","2026-10-01","2026-10-02","2026-10-05");REG=f15.OUT/"approved_screenshot_v3_registry.json"
def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+".tmp");q.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8");q.replace(p)
def load_reg():
 if not REG.exists():return {"schema":"f15_approved_screenshot_v3","dates":{}}
 x=json.loads(REG.read_text(encoding="utf-8"))
 if x.get("schema")!="f15_approved_screenshot_v3":raise RuntimeError("F15 approved renderer registry mismatch")
 return x
def run():
 time.sleep(20);r=load_reg()
 for day in DATES:
  if day in r["dates"]:continue
  p=f15.OUT/f"{day}.json"
  if not p.is_file():print(f"[F15 APPROVED WAIT] archive missing {day}",flush=True);return
  report=json.loads(p.read_text(encoding="utf-8"))
  if report.get("date")!=day or not isinstance(report.get("rows"),list):raise RuntimeError(f"F15 archive identity mismatch {p}")
  msgs=f15.flex_messages(report)
  sizes=[len(json.dumps(m["contents"],ensure_ascii=False,separators=(",",":")).encode()) for m in msgs]
  if any(n>=30000 for n in sizes):raise RuntimeError(f"F15 approved renderer >=30KB {day} {sizes}")
  f15.send(report,retry_scope="approved-screenshot-v3")
  r["dates"][day]={"sent_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),"renderer":"approved-screenshot-v3","total":report.get("total"),"parts":len(msgs),"bubble_bytes":sizes};atomic(REG,r)
  print(f"[F15 APPROVED SENT] {day} total={report.get('total')} parts={len(msgs)} bytes={sizes}",flush=True);time.sleep(1)
 print("[F15 APPROVED DONE] chronological resend complete",flush=True)
