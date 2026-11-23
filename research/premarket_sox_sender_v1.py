"""Separate LINE sender for premarket reports; distinct retry key from 17:00 maintenance."""
import json
import os
import urllib.request
import uuid


def send_premarket_flex(card, opener=urllib.request.urlopen):
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_TOKEN") or "").strip()
    to=os.getenv("LINE_TO_ID","").strip()
    if not token or not to:
        raise RuntimeError("Recognition LINE credentials missing")
    if card.get("type")!="flex" or not card.get("altText","").endswith("08:55 盤前簡報"):
        raise ValueError("Invalid premarket Flex payload")
    body=json.dumps({"to":to,"messages":[card]},ensure_ascii=False,separators=(",",":")).encode("utf-8")
    day=card["altText"][:10]
    retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"premarket-brief-0855:"+day))
    req=urllib.request.Request("https://api.line.me/v2/bot/message/push",data=body,method="POST",headers={
        "Authorization":"Bearer "+token,"Content-Type":"application/json","X-Line-Retry-Key":retry})
    with opener(req,timeout=15) as response:
        if response.status!=200:
            raise RuntimeError("Premarket LINE push HTTP "+str(response.status))
    return True
