#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone opt-in 15:30 sequential history scheduler, staging only.
Run as an independent process only after deployment approval.
"""
import datetime as dt
import os,subprocess,sys,time
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent.parent
DAILY=ROOT/"research"/"a_daily_incremental_maintenance_v1.py"
F10=ROOT/"f10_baseline_store_v1.py"
TZ=ZoneInfo("Asia/Taipei")
def tick(now,completed_day,retry_at,monotonic,call,scheduled_open):
    day=now.date().isoformat()
    if os.environ.get("A_DAILY_HISTORY_MAINTENANCE_ENABLED","0")!="1":
        return completed_day,retry_at,"DISABLED"
    if (now.hour,now.minute)<(15,30) or completed_day==day or monotonic<retry_at:
        return completed_day,retry_at,"WAIT"
    if not scheduled_open(now.date()):
        return day,retry_at,"CLOSED"
    for name,cmd in (("DAILY_K",[sys.executable,str(DAILY),"--execute"]),
                     ("F10",[sys.executable,str(F10),"--mode","update","--pause","0.15"])):
        if not Path(cmd[1]).is_file():
            return completed_day,monotonic+1800,"MISSING_"+name
        rc=call(cmd)
        if rc!=0:return completed_day,monotonic+1800,"FAILED_"+name
    return day,retry_at,"DONE"
def main():
    from twse_session_gate_v1 import is_scheduled_open
    done=None;retry=0.0
    while True:
        try:
            now=dt.datetime.now(TZ)
            done,retry,state=tick(now,done,retry,time.monotonic(),
                lambda cmd:subprocess.call(cmd,cwd=str(ROOT),env=os.environ.copy()),is_scheduled_open)
            if state not in ("WAIT","DISABLED"):
                print("[STANDALONE 15:30]",now.isoformat(),state,flush=True)
        except Exception as exc:
            retry=time.monotonic()+1800
            print("[STANDALONE 15:30] FAIL",type(exc).__name__,str(exc),flush=True)
        time.sleep(60)
if __name__=="__main__":main()
