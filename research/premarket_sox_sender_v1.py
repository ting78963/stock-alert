"""Separate LINE sender for premarket reports; distinct retry key from 17:00 maintenance."""
import json
import os
import urllib.request
from urllib.error import HTTPError
import uuid


def send_premarket_flex(card, opener=urllib.request.urlopen):
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_TOKEN") or "").strip()
    to=os.getenv("LINE_TO_ID","").strip()
    if not token or not to:
        raise RuntimeError("Recognition LINE credentials missing")
    if card.get("type")!="flex" or not card.get("altText","").endswith("08:55 盤前簡報"):
        raise ValueError("Invalid premarket Flex payload")
    from premarket_market_flex_v1 import split_premarket_flex
    messages=split_premarket_flex(card)
    body=json.dumps({"to":to,"messages":messages},ensure_ascii=False,separators=(",",":")).encode("utf-8")
    day=card["altText"][:10]
    retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"premarket-brief-0855:"+day))
    req=urllib.request.Request("https://api.line.me/v2/bot/message/push",data=body,method="POST",headers={
        "Authorization":"Bearer "+token,"Content-Type":"application/json","X-Line-Retry-Key":retry})
    try:
        with opener(req,timeout=15) as response:
            if response.status!=200:
                raise RuntimeError("Premarket LINE push HTTP "+str(response.status))
    except HTTPError as exc:
        # LINE already accepted this retry key; persist the local sent marker.
        if exc.code != 409 or not exc.headers or not exc.headers.get('x-line-accepted-request-id'):
            raise
    return True
