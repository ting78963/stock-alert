# -*- coding: utf-8 -*-
"""Standalone market-data worker. No imports from A/B, F10/F11, F15 or RESTART."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from market_data_maintenance_v1 import maintain_taiex_once
from usdtwd_cbc_maintenance_v1 import maintain_cbc_once

TPE=ZoneInfo("Asia/Taipei")

def tick(now):
    """Independent maintenance: failure in one source cannot block the other."""
    results={}
    for name,runner in (("TAIEX",maintain_taiex_once),("CBC",maintain_cbc_once)):
        try:
            results[name]=runner(now)
            if results[name] not in ("not_due","window_closed","weekend"):
                print(f"[MARKET {name}] {now.date()} {results[name]}",flush=True)
        except Exception as exc:
            results[name]="error"
            print(f"[MARKET {name} FAIL] {now.date()} {type(exc).__name__}: {exc}",flush=True)
    return results

def main():
    print("[MARKET WORKER] standalone start; no F15 or restart dependency",flush=True)
    while True:
        tick(datetime.now(TPE))
        time.sleep(300)

if __name__=="__main__":
    main()
