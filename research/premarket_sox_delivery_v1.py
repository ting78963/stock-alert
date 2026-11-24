"""Send-once 08:55 premarket coordinator, isolated from 17:00 maintenance."""
from datetime import datetime
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo
import json


TPE=ZoneInfo("Asia/Taipei")
_LOCK=Lock()

def deliver_premarket_once(now, sender, state_path, card_builder=None, session_gate=None):
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("aware datetime required")
    local=now.astimezone(TPE)
    if local.weekday()>=5 or (local.hour,local.minute)<(8,55) or (local.hour,local.minute)>=(9,0):
        return "not_due"
    with _LOCK:
        path=Path(state_path)
        if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("sent_date")==local.date().isoformat():
            return "already_sent"
        if session_gate is None:
            from twse_session_gate_v1 import is_scheduled_open
            session_gate=is_scheduled_open
        if not session_gate(local.date()):
            return "market_closed"
        if card_builder is None:
            from research.premarket_market_brief_v1 import build_market_brief
            card_builder=build_market_brief
        card=card_builder(now)
        if card.get("type")!="flex":
            raise ValueError("invalid card")
        if sender(card) is False:
            raise RuntimeError("LINE send failed")
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(".tmp")
        temp.write_text(json.dumps({"sent_date":local.date().isoformat()}),encoding="utf-8")
        temp.replace(path)
        return "sent"
