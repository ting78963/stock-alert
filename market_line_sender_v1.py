# -*- coding: utf-8 -*-
"""Market-only LINE sender; never uses GROUP_ID (limit-up group)."""
import json
import os
import urllib.request
import uuid

def send_market_flex(card):
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_TOKEN") or "").strip()
    to=os.getenv("LINE_TO_ID","").strip()
    if not token or not to:
        raise RuntimeError("Recognition LINE credentials missing")
    if card.get("type")!="flex":
        raise ValueError("Invalid market Flex payload")
    data=json.dumps({"to":to,"messages":[card]},ensure_ascii=False,separators=(",",":")).encode("utf-8")
    # Deterministic retry key guards uncertain HTTP responses against duplicate delivery.
    day=card.get("altText","")[:10]
    retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"market-data-maintenance:"+day))
    request=urllib.request.Request("https://api.line.me/v2/bot/message/push",data=data,method="POST",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json","X-Line-Retry-Key":retry})
    with urllib.request.urlopen(request,timeout=15) as response:
        if response.status not in (200,):
            raise RuntimeError("Market LINE push HTTP "+str(response.status))
    return True
