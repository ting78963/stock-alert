# -*- coding: utf-8 -*-
"""F15 | EOD signal archive + one LINE Flex per trading day.

Presentation only. Does not alter A/B/P1 recognition, F13/F14, or signal delivery.
Source of truth: persisted successful B signal events + Fugle historical 1m bars.

Visible columns:
  股票 / 代號 | 辨識 / 延遲 | 漲幅 / 收盤
Grouped P1 -> A -> B -> C, same burgundy/white/gray visual language as notifier v3.

Persistent outputs:
  STATE_ROOT/f15_eod/<date>.json       canonical report
  STATE_ROOT/f15_eod/sent_registry.json persistent LINE dedupe
"""
from __future__ import annotations
import json, os, runpy, time, urllib.error, urllib.request, uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parent
STATE_ROOT=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")))
EVENT_ROOT=STATE_ROOT/"b_live_runner_v2_p1"
OUT=STATE_ROOT/"f15_eod"
ENGINE=BASE/"fugle_b_engine_v2_p1.py"
TPE=ZoneInfo("Asia/Taipei")
ENDPOINT="https://api.line.me/v2/bot/message/push"
C_RED="#B4232C"; C_RED_DARK="#981B25"; C_TEXT="#1F2328"; C_MUTED="#8A8F98"; C_BORDER="#ECEDEF"; C_WHITE="#FFFFFF"; C_SOFT="#F7F8FA"; C_DELAY="#FDECEE"
ORDER=("P1","A","B","C")

def atomic_json(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8");tmp.replace(p)

def hm(s): return str(s or "")[:5]
def sec(s):
    h,m,x=map(int,str(s)[:8].split(":"));return h*3600+m*60+x

def pct(x):
    if x is None:return "—"
    return f"{float(x):+.2f}%"

def delay_text(seconds):
    if seconds<=0:return "—"
    m=seconds//60;s=seconds%60
    return f"+{m}m" if s==0 else f"+{m}m{s:02d}s"

def load_events(day):
    root=EVENT_ROOT/day; out=[]
    if not root.is_dir():return out
    for sd in sorted(root.iterdir()):
        if not sd.is_dir():continue
        for fn in ("p1_signal_event.json","signal_event.json"):
            p=sd/fn
            if not p.is_file():continue
            try:e=json.loads(p.read_text(encoding="utf-8"))
            except Exception as ex:raise RuntimeError(f"F15 unreadable event {p}: {ex!r}") from ex
            if e.get("date")!=day or str(e.get("stock_id","")).zfill(4)!=sd.name.zfill(4):raise RuntimeError(f"F15 event identity mismatch {p}")
            cls=str(e.get("signal_class","")).upper()
            if cls not in ORDER:raise RuntimeError(f"F15 invalid signal_class {p}: {cls}")
            if e.get("line_sent") is not True:continue
            out.append((p,e))
    # Exact event identity dedupe; retain different signal classes if historically present.
    seen=set(); ans=[]
    for p,e in out:
        k=(e["date"],str(e["stock_id"]).zfill(4),str(e["signal_class"]).upper(),str(e["recognition_time"]))
        if k in seen:continue
        seen.add(k);ans.append((p,e))
    return ans

def build_report(day):
    events=load_events(day)
    if not events:return None
    if not ENGINE.is_file():raise RuntimeError("F15 engine missing")
    M=runpy.run_path(str(ENGINE),run_name="__f15_engine__")
    key,_=M["find_key"](); rows=[]
    for _,e in events:
        sid=str(e["stock_id"]).zfill(4);rec=str(e["recognition_time"])
        obj=M["fetch"](key,sid,day); bars=M["adapt"](obj,day,sid)
        by_time={str(x["minute"])[:8]:x for x in bars}
        if rec[:8] not in by_time:raise RuntimeError(f"F15 recognition minute missing {day} {sid} {rec}")
        _,pc,_=M["fetch_prev"](key,sid,day)
        rp=float(by_time[rec[:8]]["close"]); cp=float(bars[-1]["close"])
        ds=max(0,sec(str(e["discovered_at"]))-sec(rec)) if bool(e.get("late_discovery")) else 0
        rows.append({
            "date":day,"stock_id":sid,"stock_name":str(e.get("stock_name") or sid).strip(),
            "signal_class":str(e["signal_class"]).upper(),"recognition_time":rec,
            "recognition_price":rp,"prior_close":float(pc),"recognition_gain_pct":(rp/float(pc)-1)*100,
            "discovered_at":str(e["discovered_at"]),"delay_seconds":int(ds),
            "close_price":cp,"close_gain_pct":(cp/float(pc)-1)*100,
            "late_discovery":bool(e.get("late_discovery")),"source":"Fugle historical 1m + persisted production event"
        })
    rows.sort(key=lambda x:(ORDER.index(x["signal_class"]),x["recognition_time"],x["stock_id"]))
    counts={c:sum(x["signal_class"]==c for x in rows) for c in ORDER}
    report={"schema":"f15_eod_v1","date":day,"generated_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),
            "counts":counts,"total":len(rows),"delayed":sum(x["delay_seconds"]>0 for x in rows),
            "limit_up_like":sum(x["close_gain_pct"]>=9.5 for x in rows),"rows":rows}
    atomic_json(OUT/f"{day}.json",report);return report

def text(t,size="xs",color=C_TEXT,weight=None,align=None,flex=None,wrap=False):
    x={"type":"text","text":str(t),"size":size,"color":color,"wrap":wrap}
    if weight:x["weight"]=weight
    if align:x["align"]=align
    if flex is not None:x["flex"]=flex
    return x

def row_box(r):
    left={"type":"box","layout":"vertical","flex":12,"contents":[text(r["stock_name"],"sm",C_TEXT,"bold"),text(r["stock_id"],"xxs",C_MUTED)]}
    mid_contents=[text(hm(r["recognition_time"]),"sm",C_TEXT)]
    if r["delay_seconds"]>0:
        mid_contents.append({"type":"box","layout":"vertical","backgroundColor":C_DELAY,"cornerRadius":"sm","paddingAll":"xs","margin":"xs","contents":[text(delay_text(r["delay_seconds"]),"xxs",C_RED,"bold","center")]})
    else:mid_contents.append(text("—","xxs",C_MUTED))
    mid={"type":"box","layout":"vertical","flex":9,"contents":mid_contents}
    right={"type":"box","layout":"vertical","flex":11,"alignItems":"flex-end","contents":[text(pct(r["recognition_gain_pct"]),"sm",C_RED),text(pct(r["close_gain_pct"]),"sm",C_RED,"bold",margin if False else None)]}
    return {"type":"box","layout":"horizontal","alignItems":"center","paddingTop":"sm","paddingBottom":"sm","contents":[left,mid,right]}

def section(cls,rows):
    head={"type":"box","layout":"horizontal","alignItems":"center","margin":"lg","contents":[text(cls,"xl",C_RED,"bold",flex=0),{"type":"separator","margin":"md","color":C_RED},{"type":"text","text":f"共 {len(rows)} 檔","size":"sm","weight":"bold","color":C_RED,"margin":"md","flex":0}]}
    cols={"type":"box","layout":"horizontal","backgroundColor":C_SOFT,"paddingAll":"sm","contents":[text("股票 / 代號","xxs",C_MUTED,flex=12),text("辨識 / 延遲","xxs",C_MUTED,flex=9),text("漲幅 / 收盤","xxs",C_MUTED,align="end",flex=11)]}
    body=[head,cols]
    for i,r in enumerate(rows):
        body.append(row_box(r))
        if i<len(rows)-1:body.append({"type":"separator","color":C_BORDER})
    return {"type":"box","layout":"vertical","contents":body}

def build_flex(report):
    day=report["date"].replace("-"," / ")
    contents=[{"type":"box","layout":"horizontal","alignItems":"center","contents":[text("↗","lg",C_RED,"bold",flex=0),{"type":"text","text":"BUY SIGNAL","size":"sm","color":C_RED,"weight":"bold","margin":"sm","flex":0},{"type":"separator","margin":"md","color":C_BORDER},{"type":"text","text":"盤後訊號統計","size":"xs","color":C_MUTED,"margin":"md","flex":0}]},text(day,"xxl",C_TEXT,"bold"),{"type":"separator","color":C_BORDER,"margin":"lg"}]
    for cls in ORDER:
        rr=[r for r in report["rows"] if r["signal_class"]==cls]
        if rr:contents.append(section(cls,rr))
    c=report["counts"]
    contents += [{"type":"separator","color":C_BORDER,"margin":"xl"},
      {"type":"box","layout":"horizontal","margin":"md","contents":[text(f"P1 {c['P1']}｜A {c['A']}｜B {c['B']}｜C {c['C']}","xs",C_RED,"bold",flex=1),text(f"總計 {report['total']} 檔","xs",C_TEXT,"bold","end",1)]},
      {"type":"box","layout":"horizontal","margin":"sm","contents":[text(f"◷ A延遲 {report['delayed']} 檔","xs",C_MUTED,flex=1),text(f"★ 漲停 {report['limit_up_like']} 檔","xs",C_RED,"bold","end",1)]},
      {"type":"box","layout":"vertical","backgroundColor":C_RED_DARK,"cornerRadius":"lg","paddingAll":"md","margin":"lg","contents":[text("▲   盤後訊號統計","md",C_WHITE,"bold","center")]},
      {"type":"box","layout":"horizontal","margin":"md","contents":[text("歷史統計・僅供參考","xxs",C_MUTED,flex=1),text("Trade Smart | Your Edge","xxs",C_MUTED,"end",1)]}]
    return {"type":"flex","altText":f"盤後訊號統計｜{report['date']}｜共 {report['total']} 檔"[:400],"contents":{"type":"bubble","size":"mega","body":{"type":"box","layout":"vertical","paddingAll":"xl","contents":contents}}}

def credentials():
    token=(os.getenv("LINE_CHANNEL_ACCESS_TOKEN","").strip() or os.getenv("LINE_TOKEN","").strip())
    to=(os.getenv("LINE_TO_ID","").strip() or os.getenv("GROUP_ID","").strip())
    if not token or not to:raise RuntimeError("F15 LINE credentials missing")
    return token,to

def send_report(report):
    token,to=credentials();flex=build_flex(report)
    data=json.dumps({"to":to,"messages":[flex],"notificationDisabled":False},ensure_ascii=False).encode("utf-8")
    retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"f15-eod-v1:"+report["date"]))
    req=urllib.request.Request(ENDPOINT,data=data,method="POST",headers={"Content-Type":"application/json","Authorization":"Bearer "+token,"X-Line-Retry-Key":retry})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:status=r.status;body=r.read().decode("utf-8",errors="replace")
    except urllib.error.HTTPError as ex:raise RuntimeError(f"F15 LINE HTTP {ex.code}: "+ex.read().decode("utf-8",errors="replace")[:800]) from ex
    if status!=200:raise RuntimeError(f"F15 LINE status={status} body={body[:500]}")
    return status

def registry():
    p=OUT/"sent_registry.json"
    if not p.exists():return p,{"schema":"f15_sent_v1","dates":{}}
    x=json.loads(p.read_text(encoding="utf-8"))
    if x.get("schema")!="f15_sent_v1" or not isinstance(x.get("dates"),dict):raise RuntimeError("F15 sent registry schema mismatch")
    return p,x

def process_day(day,send=True):
    p,reg=registry()
    if day in reg["dates"]:return "already_sent"
    report=build_report(day)
    if report is None:return "no_events"
    if not send:return report
    send_report(report)
    reg["dates"][day]={"sent_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),"total":report["total"]}
    atomic_json(p,reg);print(f"[F15 SENT] {day} total={report['total']} delayed={report['delayed']}",flush=True);return "sent"

def recent_days(n=7):
    d=datetime.now(TPE).date();return [(d-timedelta(days=i)).isoformat() for i in range(n,-1,-1)]

def loop():
    """Daemon-safe: backfill recent unsent completed sessions on startup; then check after 13:40."""
    OUT.mkdir(parents=True,exist_ok=True)
    while True:
        now=datetime.now(TPE)
        try:
            # Current day is eligible only after 13:40; older days are always eligible.
            today=now.date().isoformat()
            for day in recent_days(7):
                if day==today and (now.hour,now.minute)<(13,40):continue
                try:process_day(day,send=True)
                except BaseException as e:print(f"[F15 FAIL] {day} {type(e).__name__}: {e}",flush=True)
        except BaseException as e:print(f"[F15 LOOP FAIL] {type(e).__name__}: {e}",flush=True)
        time.sleep(300)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--date");ap.add_argument("--send",action="store_true");a=ap.parse_args()
    day=a.date or datetime.now(TPE).date().isoformat();x=process_day(day,send=a.send)
    if isinstance(x,dict):print(json.dumps(x,ensure_ascii=False,indent=2))
    else:print(x)
