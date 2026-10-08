#!/usr/bin/env python3
"""Independent queue audit archive maintenance loop. Never deletes source files."""
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
ARCHIVER = Path(__file__).with_name("a_queue_archive_v1.py")
INTERVAL_SECONDS = 3600

def once():
    now = dt.datetime.now(TZ)
    # Archive yesterday or earlier only; avoid market hours and live writes.
    if not (now.hour < 8 or now.hour >= 15):
        print("[QUEUE_ARCHIVE] SKIP trading-hours window", flush=True)
        return
    cmd = [sys.executable, str(ARCHIVER), "--mode", "compress",
           "--min-age-minutes", "120"]
    result = subprocess.run(cmd, timeout=600, check=False)
    print(f"[QUEUE_ARCHIVE] completed exit={result.returncode}", flush=True)

def loop():
    print("[QUEUE_ARCHIVE] background archive loop started; no deletion", flush=True)
    while True:
        try:
            once()
        except Exception as exc:
            print(f"[QUEUE_ARCHIVE] ERROR {type(exc).__name__}: {exc}", flush=True)
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    loop()
