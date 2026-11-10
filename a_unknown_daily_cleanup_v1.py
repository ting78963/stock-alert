#!/usr/bin/env python3
"""Run bounded-memory UNKNOWN audit cleanup after daily data maintenance."""
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from fugle_a_scanner_v2_4 import maintain_unknown_event_log

if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    result = maintain_unknown_event_log(day)
    if result.get("skipped_market"):
        raise SystemExit("UNKNOWN cleanup blocked during market hours")
    print(json.dumps(result, ensure_ascii=False), flush=True)
