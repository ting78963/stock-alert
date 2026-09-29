# -*- coding: utf-8 -*-
"""
LINE SIGNAL NOTIFIER v2 | A/B/C/P1
=======================
Independent notification layer for B Engine A/B/C/P1 signal event JSON.

Uses LINE Messaging API push messages (NOT the discontinued LINE Notify).

Required environment variables for REAL send:
    LINE_CHANNEL_ACCESS_TOKEN
    LINE_TO_ID
where LINE_TO_ID is a userId/groupId/roomId valid for your Messaging API channel.

Default mode is DRY RUN: validates the signal event and renders the exact message,
but sends nothing. Add --send for a real push.

Safety / dedupe:
- requires supported ABC/P1 event schema + causal time fields
- refuses line_sent=true
- real send uses X-Line-Retry-Key derived deterministically from date+stock+class+live_known_time
- after HTTP 200, atomically marks line_sent=true in the event
- never changes trading logic, signal class, price, or timing

Estimated runtime: <1 sec dry-run; ~1-3 sec real send.
Main bottleneck: LINE HTTPS request.
"""
from __future__ import annotations
import argparse, hashlib, json, os, uuid, urllib.request, urllib.error
from pathlib import Path

ENDPOINT="https://api.line.me/v2/bot/message/push"

def stop(s):
    print("\n"+"="*120)
    print("NOTIFIER AUDIT FAILED -> STOP -> NO LINE SEND")
    print("="*120); print(s); raise SystemExit(2)

def atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def valid_time(x):
    import re
    return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}",str(x or "")))

def load_event(path):
    try:e=json.loads(path.read_text(encoding="utf-8"))
    except Exception as ex:stop(f"Cannot read event: {ex!r}")
    common=["schema","date","stock_id","signal_class","discovered_at",
            "recognition_time","live_known_time","late_discovery"]
    miss=[k for k in common if k not in e]
    if miss:stop(f"Missing event fields: {miss}")
    cls=e["signal_class"]; schema=e["schema"]
    if cls in ("A","B","C"):
        if schema!="b_signal_event_v1":stop(f"Unsupported ABC schema: {schema}")
        req=["a2_end","a2_vr","early_high_pct"]
        miss=[k for k in req if k not in e]
        if miss:stop(f"Missing ABC event fields: {miss}")
        times=("discovered_at","recognition_time","live_known_time","a2_end")
    elif cls=="P1":
        if schema!="b_signal_event_v2":stop(f"Unsupported P1 schema: {schema}")
        req=["a1_time","p1_time","post_p1_entry_time"]
        miss=[k for k in req if k not in e]
        if miss:stop(f"Missing P1 event fields: {miss}")
        times=("discovered_at","recognition_time","live_known_time",
               "a1_time","p1_time","post_p1_entry_time")
    else:stop(f"Invalid signal class: {cls}")
    if not all(valid_time(e[k]) for k in times):stop("Invalid causal time format.")
    if e.get("line_sent") is True:stop("This event is already marked line_sent=true (persistent dedupe).")
    return e

def render(e):
    late="是" if e["late_discovery"] else "否"
    if e.get("execution_time") and e.get("execution_open") is not None:
        ex=f"\n買進：{e['execution_time']} OPEN {float(e['execution_open']):g}"
    else:ex="\n執行：等待 live_known_time 後第一個完成分鐘 OPEN"
    if e["signal_class"]=="P1":
        return (
            f"【趨勢買進訊號｜P1】\n"
            f"{e['stock_id']}｜{e['date']}\n"
            f"實戰可知時間：{e['live_known_time']}\n"
            f"Frontier辨識：{e['recognition_time']}\n"
            f"A1：{e['a1_time']}\n"
            f"P1 Body：{e['p1_time']}\n"
            f"Post-P1 baseline：{e['post_p1_entry_time']}\n"
            f"晚發現重建：{late}{ex}"
        )
    return (
        f"【趨勢買進訊號｜{e['signal_class']}】\n"
        f"{e['stock_id']}｜{e['date']}\n"
        f"實戰可知時間：{e['live_known_time']}\n"
        f"趨勢辨識時間：{e['recognition_time']}\n"
        f"A2：{e['a2_end']}\n"
        f"A2 VR：{float(e['a2_vr']):.4f}\n"
        f"Early High：{float(e['early_high_pct']):.2f}%\n"
        f"晚發現重建：{late}{ex}"
    )

def retry_key(e):
    raw=f"{e['date']}|{e['stock_id']}|{e['signal_class']}|{e['live_known_time']}"
    # UUID v5 gives deterministic valid UUID for LINE retry semantics.
    return str(uuid.uuid5(uuid.NAMESPACE_URL,"b-signal:"+raw))

def send(e,text):
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN","") or os.getenv("LINE_TOKEN","")).strip()
    to=(os.getenv("LINE_TO_ID","") or os.getenv("GROUP_ID","")).strip()
    if not token:stop("LINE_CHANNEL_ACCESS_TOKEN is not set.")
    if not to:stop("LINE_TO_ID is not set.")
    body=json.dumps({"to":to,"messages":[{"type":"text","text":text}],
                     "notificationDisabled":False},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(
        ENDPOINT,data=body,method="POST",
        headers={"Content-Type":"application/json",
                 "Authorization":"Bearer "+token,
                 "X-Line-Retry-Key":retry_key(e)})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            status=r.status; payload=r.read().decode("utf-8",errors="replace")
    except urllib.error.HTTPError as x:
        detail=x.read().decode("utf-8",errors="replace")[:1000]
        stop(f"LINE HTTP {x.code}: {detail}")
    except Exception as x:stop(f"LINE request failed: {x!r}")
    if status!=200:stop(f"Unexpected LINE status {status}: {payload[:500]}")
    return status,payload

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("event",help="path to b_signal_event_v1 JSON")
    ap.add_argument("--send",action="store_true",help="actually send LINE push")
    a=ap.parse_args(); path=Path(a.event)
    if not path.is_file():stop(f"Event not found: {path}")
    e=load_event(path); text=render(e)

    print("="*120)
    print("LINE SIGNAL NOTIFIER v2 | A/B/C/P1")
    print("="*120)
    print("Mode:", "REAL SEND" if a.send else "DRY RUN")
    print("Event:",path)
    print("Retry key:",retry_key(e))
    print("\nMESSAGE PREVIEW\n"+"-"*120)
    print(text)
    print("-"*120)

    if not a.send:
        print("\nDRY RUN PASS -> NO LINE SEND")
        return

    status,payload=send(e,text)
    e["line_sent"]=True
    from datetime import datetime, timezone
    e["line_sent_at_utc"]=datetime.now(timezone.utc).isoformat(timespec="seconds")
    e["line_retry_key"]=retry_key(e)
    atomic_json(path,e)
    print(f"\nLINE SEND PASS | HTTP {status}")
    print("Event atomically updated: line_sent=true")

if __name__=="__main__":main()