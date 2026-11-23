# -*- coding: utf-8 -*-
"""Send-once coordination for combined market report; sender injected by caller.

The callback MUST raise on unsuccessful LINE response. This module never accesses
LINE credentials, and never starts a production scheduler.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from market_maintenance_report_v1 import build_from_stores

TPE=ZoneInfo("Asia/Taipei")
STATE=Path(os.getenv("MARKET_REPORT_SENT_STATE","/var/data/stock-alert/market_data/market_report_sent.json"))

def deliver_once(now,send_flex,state_path=STATE,report_builder=build_from_stores):
    """Exactly one successful invocation per date in a single worker process.

    Failed callbacks do not mark sent. Concurrent calls in the same process
    are serialized. Across processes use one shared worker/lock.
    """
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    local=now.astimezone(TPE)
    if local.weekday()>=5 or not (17<=local.hour<18):
        return "not_due"
    if not callable(send_flex):
        raise TypeError("send_flex callback required")
    day=local.date().isoformat()
    import threading
    with _LOCK:
        path=Path(state_path)
        if path.exists():
            data=json.loads(path.read_text(encoding="utf-8"))
            if data.get("sent_date")==day:
                return "already_sent"
        card=report_builder(now)
        if "未完成" in card.get("altText",""):
            return "waiting_for_data"
        if card.get("type")!="flex":
            raise ValueError("Invalid LINE Flex report")
        # The sender must confirm success or raise. Only then persist sent marker.
        response=send_flex(card)
        # False is an explicit failure; None is allowed for existing senders that
        # raise on HTTP errors and return no value.
        if response is False:
            raise RuntimeError("LINE sender reported failure")
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(path.suffix+".tmp")
        temp.write_text(json.dumps({"sent_date":day},ensure_ascii=False),encoding="utf-8")
        temp.replace(path)
        return "sent"

import threading
_LOCK=threading.Lock()
