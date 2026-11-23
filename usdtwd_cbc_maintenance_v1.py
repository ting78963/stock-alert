# -*- coding: utf-8 -*-
"""Isolated CBC close maintenance, no effect on A/B, F15 or LINE sending."""
from datetime import datetime
from zoneinfo import ZoneInfo
from usdtwd_cbc_store_v1 import read_store, update

TPE=ZoneInfo("Asia/Taipei")

def maintain_cbc_once(now):
    """Attempt once after 17:00 Taiwan time on weekdays; never mark stale data updated."""
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    local=now.astimezone(TPE)
    if local.weekday()>=5:
        return "weekend"
    if (local.hour,local.minute)<(17,0):
        return "not_due"
    if (local.hour,local.minute)>=(18,0):
        return "window_closed"
    existing=read_store()
    if existing and existing[-1]["date"]==local.date().isoformat():
        return "already_updated"
    result=update(as_of=local.date())
    if result["latest"]!=local.date().isoformat():
        return "not_published"
    return "updated"
