# -*- coding: utf-8 -*-
"""Opt-in A-only VCP LINE notification; no changes to B handoff dedupe."""
import json
import os
import uuid
import urllib.request
import urllib.error

from a_vcp_flex_v1 import build_vcp_flex

ENDPOINT = "https://api.line.me/v2/bot/message/push"


def make_event(row, decision, day, recognition_time):
    """Use only current snapshot and pinned VCP watch/track; never guess pivot."""
    watch = decision.get("watch") or {}
    track = decision.get("pivot_track") or {}
    pivot = watch.get("pivot") if watch.get("pivot") is not None else track.get("pivot")
    return {
        "stock_id": str(row["stock_id"]),
        "name": str(row.get("name") or row["stock_id"]),
        "date": day,
        "recognition_time": recognition_time,
        "pivot": pivot,
        "price": row.get("close"),
        "change_pct": row.get("change_rate"),
        "vol_ratio": decision.get("raw_vr5"),
        "volume_zhang": row.get("total_volume"),
    }


def notify_once(event, sent, *, sender=None):
    """Success-only dedupe; stable LINE retry key for uncertain transport failures."""
    key = str(event["date"]) + "|" + str(event["stock_id"])
    if key in sent:
        return False
    # A proposal can be pending; do not label it a confirmed breakout below Pivot.
    pivot = float(event["pivot"])
    price = float(event["price"])
    if not (price > pivot):
        return False
    flex = build_vcp_flex(event)  # validate before any network call
    if sender is None:
        sender = send_line
    sender(flex, key)
    sent[key] = True
    return True


def send_line(flex, key):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip() or os.getenv("LINE_TOKEN", "").strip()
    # Dedicated destination required: never fall back to the existing production B group.
    to = os.getenv("A_VCP_LINE_TO_ID", "").strip()
    if not token or not to:
        raise RuntimeError("VCP LINE token or dedicated A_VCP_LINE_TO_ID missing")
    payload = json.dumps({"to": to, "messages": [flex]}, ensure_ascii=False).encode("utf-8")
    retry = str(uuid.uuid5(uuid.NAMESPACE_URL, "a-vcp-line:" + key))
    req = urllib.request.Request(ENDPOINT, data=payload, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + token,
        "X-Line-Retry-Key": retry,
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("VCP LINE status " + str(response.status))
    except urllib.error.HTTPError as exc:
        # LINE retry-key duplicate acceptance is 409; other errors retry next scan.
        if exc.code != 409:
            raise
