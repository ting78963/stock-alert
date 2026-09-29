# -*- coding: utf-8 -*-
"""
LINE SIGNAL NOTIFIER v3 | A/B/C/P1 FLEX
=======================================
Notification-only layer. Does NOT change recognition/trading logic.

Dynamic:
- stock_id
- stock_name (if present in event; otherwise stock_id is shown)
- signal_class
- recognition_time

Locked card copy/statistics:
P1 | 當沖首選 | +10% | 約3日 | 7日內 | 約+17% | ⚡ 當沖 +1% 勝率 66.8%
A  | 穩定延伸 | +10% | 約4日 | 7日內 | 約+17%
B  | 高延伸   | +15% | 約4日 | 8日內 | 約+23%
C  | 高爆發・高回吐 | +20% | 約5日 | 10日內 | 約+21%

Default = DRY RUN. Use --send only after preview is confirmed.
"""
from __future__ import annotations
import argparse, json, os, re, uuid, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://api.line.me/v2/bot/message/push"
C_RED = "#B4232C"
C_RED_DARK = "#981B25"
C_TEXT = "#1F2328"
C_MUTED = "#8A8F98"
C_BORDER = "#ECEDEF"
C_GOLD = "#D9A400"
C_WHITE = "#FFFFFF"

CARD = {
    "P1": {"title":"當沖首選","desc":"當沖優勢明顯，未達標仍具後續延伸性。","target":"+10%","common":"約3日","majority":"7日內","extension":"約+17%","daytrade":"⚡ 當沖 +1% 勝率 66.8%"},
    "A": {"title":"穩定延伸","desc":"走勢相對穩定，具延伸性，適合中短期持有。","target":"+10%","common":"約4日","majority":"7日內","extension":"約+17%"},
    "B": {"title":"高延伸","desc":"具較強延伸動能，趨勢持續性佳。","target":"+15%","common":"約4日","majority":"8日內","extension":"約+23%"},
    "C": {"title":"高爆發・高回吐","desc":"前段爆發力強，但獲利回吐也相對較大，適合積極操作。","target":"+20%","common":"約5日","majority":"10日內","extension":"約+21%"},
}
def stop(msg):
    print("\n"+"="*110); print("NOTIFIER AUDIT FAILED -> STOP -> NO LINE SEND"); print("="*110); print(msg); raise SystemExit(2)
def atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)
def valid_time(x): return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}",str(x or "")))
def load_event(path):
    try:e=json.loads(path.read_text(encoding="utf-8"))
    except Exception as ex:stop(f"Cannot read event: {ex!r}")
    common=["schema","date","stock_id","signal_class","discovered_at","recognition_time","live_known_time","late_discovery"]
    miss=[k for k in common if k not in e]
    if miss:stop(f"Missing event fields: {miss}")
    cls=str(e["signal_class"]).upper();e["signal_class"]=cls
    if cls in ("A","B","C"):
        if e["schema"]!="b_signal_event_v1":stop(f"Unsupported ABC schema: {e['schema']}")
        req=["a2_end","a2_vr","early_high_pct"];miss=[k for k in req if k not in e]
        if miss:stop(f"Missing ABC event fields: {miss}")
        times=("discovered_at","recognition_time","live_known_time","a2_end")
    elif cls=="P1":
        if e["schema"]!="b_signal_event_v2":stop(f"Unsupported P1 schema: {e['schema']}")
        req=["a1_time","p1_time","post_p1_entry_time"];miss=[k for k in req if k not in e]
        if miss:stop(f"Missing P1 event fields: {miss}")
        times=("discovered_at","recognition_time","live_known_time","a1_time","p1_time","post_p1_entry_time")
    else:stop(f"Invalid signal class: {cls}")
    if not all(valid_time(e[k]) for k in times):stop("Invalid causal time format.")
    # Normal dedupe is line_sent. A one-time v2->v3 presentation migration may
    # intentionally resend an already-delivered event as the approved Flex card.
    if e.get("line_sent") is True and not getattr(load_event,"allow_flex_migration",False):
        stop("This event is already marked line_sent=true (persistent dedupe).")
    return e
def stock_display(e):
    sid=str(e["stock_id"]);name=str(e.get("stock_name") or e.get("name") or e.get("stockName") or "").strip();return (name if name else sid,sid)
def stat_cell(label,value):
    return {"type":"box","layout":"vertical","flex":1,"alignItems":"center","contents":[{"type":"text","text":label,"size":"xxs","color":C_MUTED,"align":"center","wrap":True},{"type":"text","text":value,"size":"sm","color":C_RED,"weight":"bold","align":"center","margin":"sm"}]}
def build_flex(e):
    cls=e["signal_class"];spec=CARD[cls];name,sid=stock_display(e);recog=str(e["recognition_time"])[:5]
    contents=[
      {"type":"box","layout":"horizontal","alignItems":"center","contents":[{"type":"text","text":"↗","size":"lg","color":C_RED,"weight":"bold","flex":0},{"type":"text","text":"BUY SIGNAL","size":"xs","color":C_RED,"weight":"bold","margin":"sm","flex":0},{"type":"separator","margin":"md","color":C_BORDER},{"type":"text","text":"趨勢確認","size":"xs","color":C_MUTED,"margin":"md","flex":0}]},
      {"type":"text","text":name,"size":"xxl","weight":"bold","color":C_TEXT,"margin":"xl"},{"type":"text","text":sid,"size":"sm","color":C_MUTED,"margin":"xs"},
      {"type":"box","layout":"horizontal","alignItems":"center","margin":"lg","contents":[{"type":"text","text":cls,"size":"xl","weight":"bold","color":C_RED,"flex":0},{"type":"separator","margin":"md","color":C_RED},{"type":"text","text":spec["title"],"size":"md","weight":"bold","color":C_RED,"margin":"md","flex":0}]}
    ]
    if cls=="P1":contents.append({"type":"text","text":spec["daytrade"],"size":"sm","weight":"bold","color":C_GOLD,"margin":"md"})
    contents += [
      {"type":"text","text":spec["desc"],"size":"sm","color":"#676C75","wrap":True,"margin":"md"},{"type":"separator","color":C_BORDER,"margin":"xl"},
      {"type":"box","layout":"horizontal","margin":"lg","spacing":"sm","contents":[stat_cell("目標漲幅",spec["target"]),stat_cell("常見達標",spec["common"]),stat_cell("多數達標",spec["majority"]),stat_cell("15日最大延伸",spec["extension"])]},
      {"type":"box","layout":"vertical","backgroundColor":C_RED_DARK,"cornerRadius":"lg","paddingAll":"md","margin":"xl","contents":[{"type":"text","text":"▲   立即買進","size":"md","weight":"bold","color":C_WHITE,"align":"center"}]},
      {"type":"text","text":f"◷  趨勢已成立  {recog}","size":"sm","color":C_MUTED,"align":"center","margin":"md"},{"type":"separator","color":C_BORDER,"margin":"xl"},
      {"type":"box","layout":"horizontal","margin":"md","contents":[{"type":"text","text":"歷史統計・僅供參考","size":"xxs","color":C_MUTED,"flex":1},{"type":"text","text":"Trade Smart | Your Edge","size":"xxs","color":C_MUTED,"align":"end","flex":1}]}
    ]
    return {"type":"flex","altText":f"BUY SIGNAL｜{name} {sid}｜{cls} {spec['title']}｜立即買進"[:400],"contents":{"type":"bubble","size":"mega","body":{"type":"box","layout":"vertical","paddingAll":"xl","contents":contents}}}
def retry_key(e):
    # Stable signal identity: late discovery/replay must not create a new LINE retry key.
    raw=f"{e['date']}|{e['stock_id']}|{e['signal_class']}|{e['recognition_time']}"
    ns="b-signal-flex-v3-migration:" if getattr(retry_key,"flex_migration",False) else "b-signal:"
    return str(uuid.uuid5(uuid.NAMESPACE_URL,ns+raw))
def credentials():
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN","").strip() or os.getenv("LINE_TOKEN","").strip());to=(os.getenv("LINE_TO_ID","").strip() or os.getenv("GROUP_ID","").strip())
    if not token:stop("LINE token is not set (LINE_CHANNEL_ACCESS_TOKEN or LINE_TOKEN).")
    if not to:stop("LINE destination is not set (LINE_TO_ID or GROUP_ID).")
    return token,to
def send(e,flex):
    token,to=credentials();data=json.dumps({"to":to,"messages":[flex],"notificationDisabled":False},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(ENDPOINT,data=data,method="POST",headers={"Content-Type":"application/json","Authorization":"Bearer "+token,"X-Line-Retry-Key":retry_key(e)})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:status=r.status;payload=r.read().decode("utf-8",errors="replace")
    except urllib.error.HTTPError as ex:stop(f"LINE HTTP {ex.code}: "+ex.read().decode("utf-8",errors="replace")[:1000])
    except Exception as ex:stop(f"LINE request failed: {ex!r}")
    if status!=200:stop(f"Unexpected LINE status {status}: {payload[:500]}")
    return status
def main():
    ap=argparse.ArgumentParser();ap.add_argument("event");ap.add_argument("--send",action="store_true");ap.add_argument("--preview-json",action="store_true");ap.add_argument("--stock-name",default="");ap.add_argument("--flex-migration",action="store_true");a=ap.parse_args()
    path=Path(a.event)
    if not path.is_file():stop(f"Event not found: {path}")
    load_event.allow_flex_migration=bool(a.flex_migration)
    retry_key.flex_migration=bool(a.flex_migration)
    e=load_event(path)
    if a.stock_name.strip():e["stock_name"]=a.stock_name.strip()
    flex=build_flex(e);spec=CARD[e["signal_class"]];name,sid=stock_display(e)
    print("="*110);print("LINE SIGNAL NOTIFIER v3 | A/B/C/P1 FLEX");print("="*110);print("Mode:","REAL SEND" if a.send else "DRY RUN");print("Event:",path);print("Stock:",f"{name} {sid}");print("Signal:",f"{e['signal_class']} | {spec['title']}");print("Recognition:",e["recognition_time"]);print("Retry key:",retry_key(e))
    if a.preview_json:print(json.dumps(flex,ensure_ascii=False,indent=2))
    if not a.send:print("\nDRY RUN PASS -> NO LINE SEND");return
    status=send(e,flex)
    e["line_sent"]=True
    e["line_sent_at_utc"]=datetime.now(timezone.utc).isoformat(timespec="seconds")
    e["line_retry_key"]=retry_key(e)
    e["flex_v3_sent"]=True
    e["flex_v3_sent_at_utc"]=e["line_sent_at_utc"]
    atomic_json(path,e)
    print(f"\nLINE FLEX SEND PASS | HTTP {status}")
    print("Event atomically updated: line_sent=true, flex_v3_sent=true")
if __name__=="__main__":main()
