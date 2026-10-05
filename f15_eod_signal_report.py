# -*- coding: utf-8 -*-
"""F15 EOD signal archive + one compact LINE Flex per completed trading day. Presentation only."""
from __future__ import annotations
import json,os,runpy,time,urllib.request,urllib.error,uuid
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path(__file__).resolve().parent;STATE=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")));EVENTS=STATE/"b_live_runner_v2_p1";OUT=STATE/"f15_eod";ENGINE=BASE/"fugle_b_engine_v2_p1.py"
TPE=ZoneInfo("Asia/Taipei");ORDER=("P1","A","B","C");ENDPOINT="https://api.line.me/v2/bot/message/push";RED="#B4232C";DARK="#981B25";TEXT="#1F2328";MUTED="#8A8F98";BORDER="#ECEDEF";WHITE="#FFFFFF";SOFT="#F7F8FA"
def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+".tmp");q.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8");q.replace(p)
def normt(s):s=str(s or "").strip();return s[:5] if len(s)>=5 else s
def secs(s):p=normt(s).split(":");return int(p[0])*3600+int(p[1])*60
def pc(x):return f"{float(x):+.2f}%"
def dtxt(x):m,s=divmod(int(x),60);return "—" if x<=0 else (f"+{m}m" if not s else f"+{m}m{s:02d}s")
def tx(s,size="xs",color=TEXT,weight=None,align=None,flex=None):
 x={"type":"text","text":str(s),"size":size,"color":color,"wrap":True}
 if weight in ("bold","regular"):x["weight"]=weight
 if align in ("start","center","end"):x["align"]=align
 if flex is not None:x["flex"]=int(flex)
 return x
def load_events(day):
 root=EVENTS/day;a=[]
 if not root.is_dir():return a
 for sd in sorted(root.iterdir()):
  if not sd.is_dir():continue
  for fn in ("p1_signal_event.json","signal_event.json"):
   p=sd/fn
   if not p.is_file():continue
   e=json.loads(p.read_text(encoding="utf-8"));sid=str(e.get("stock_id","")).zfill(4);cls=str(e.get("signal_class","")).upper()
   if e.get("date")!=day or sid!=sd.name.zfill(4):raise RuntimeError(f"F15 event identity mismatch {p}")
   if cls not in ORDER:raise RuntimeError(f"F15 invalid class {p}")
   if e.get("line_sent") is True:a.append(e)
 seen=set();out=[]
 for e in a:
  k=(e["date"],str(e["stock_id"]).zfill(4),e["signal_class"],e["recognition_time"])
  if k not in seen:seen.add(k);out.append(e)
 return out
def build_report(day):
 ev=load_events(day)
 if not ev:return None
 M=runpy.run_path(str(ENGINE),run_name="__f15_engine__");key,_=M["find_key"]();rows=[]
 for e in ev:
  sid=str(e["stock_id"]).zfill(4);rec=normt(e["recognition_time"]);bars=M["adapt"](M["fetch"](key,sid,day),day,sid);bt={normt(b["minute"]):b for b in bars}
  if rec in bt:rp=float(bt[rec]["close"]);price_minute=rec
  elif str(e.get("signal_class","")).upper() in ("A","B","C") and e.get("frozen_early_price") is not None:rp=float(e["frozen_early_price"]);price_minute="event:frozen_early_price"
  else:raise RuntimeError(f"F15 missing recognition price {day} {sid} {rec}")
  _,prev,_=M["fetch_prev"](key,sid,day);close=float(bars[-1]["close"]);delay=max(0,secs(e["discovered_at"])-secs(rec)) if e.get("late_discovery") is True else 0
  rows.append({"date":day,"stock_id":sid,"stock_name":str(e.get("stock_name") or sid),"signal_class":str(e["signal_class"]).upper(),"recognition_time":rec,"recognition_price":rp,"recognition_price_source":price_minute,"prior_close":prev,"recognition_gain_pct":(rp/prev-1)*100,"discovered_at":e["discovered_at"],"delay_seconds":delay,"close_price":close,"close_gain_pct":(close/prev-1)*100,"source":"Fugle historical 1m + production event"})
 rows.sort(key=lambda r:(ORDER.index(r["signal_class"]),r["recognition_time"],r["stock_id"]));counts={c:sum(r["signal_class"]==c for r in rows) for c in ORDER};x={"schema":"f15_eod_v1","date":day,"generated_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),"counts":counts,"total":len(rows),"delayed":sum(r["delay_seconds"]>0 for r in rows),"limit_up_like":sum(r["close_gain_pct"]>=9.5 for r in rows),"rows":rows};atomic(OUT/f"{day}.json",x);return x
def compact_row(r):
 return {"type":"box","layout":"horizontal","paddingTop":"sm","paddingBottom":"sm","contents":[tx(f"{r['stock_name']}\n{r['stock_id']}","xs",TEXT,"bold",flex=12),tx(f"{r['recognition_time']}\n{dtxt(r['delay_seconds'])}","xs",TEXT,flex=9),tx(f"{pc(r['recognition_gain_pct'])}\n{pc(r['close_gain_pct'])}","xs",RED,"bold","end",11)]}
def section(c,rr):
 z=[{"type":"box","layout":"horizontal","margin":"lg","contents":[tx(c,"lg",RED,"bold",flex=1),tx(f"共 {len(rr)} 檔","xs",RED,"bold","end",1)]},{"type":"box","layout":"horizontal","backgroundColor":SOFT,"paddingAll":"sm","contents":[tx("股票 / 代號","xxs",MUTED,flex=12),tx("辨識 / 延遲","xxs",MUTED,flex=9),tx("漲幅 / 收盤","xxs",MUTED,align="end",flex=11)]}]
 for r in rr:z.append(compact_row(r))
 return {"type":"box","layout":"vertical","contents":z}
def flex(report):
 body=[{"type":"box","layout":"horizontal","contents":[tx("↗ BUY SIGNAL","sm",RED,"bold",flex=1),tx("盤後訊號統計","xs",MUTED,"regular","end",1)]},tx(report["date"].replace("-"," / "),"xl",TEXT,"bold"),{"type":"separator","color":BORDER,"margin":"md"}]
 for c in ORDER:
  rr=[r for r in report["rows"] if r["signal_class"]==c]
  if rr:body.append(section(c,rr))
 c=report["counts"];body.extend([{"type":"separator","color":BORDER,"margin":"lg"},{"type":"box","layout":"horizontal","margin":"sm","contents":[tx(f"P1 {c['P1']}｜A {c['A']}｜B {c['B']}｜C {c['C']}","xxs",RED,"bold",flex=1),tx(f"總計 {report['total']} 檔","xxs",TEXT,"bold","end",1)]},{"type":"box","layout":"horizontal","contents":[tx(f"◷ A延遲 {report['delayed']} 檔","xxs",MUTED,flex=1),tx(f"★ 漲停 {report['limit_up_like']} 檔","xxs",RED,"bold","end",1)]},{"type":"box","layout":"vertical","backgroundColor":DARK,"cornerRadius":"lg","paddingAll":"sm","margin":"md","contents":[tx("▲   盤後訊號統計","sm",WHITE,"bold","center")]},tx("歷史統計・僅供參考     Trade Smart | Your Edge","xxs",MUTED,"regular","center")]);return {"type":"flex","altText":f"盤後訊號統計｜{report['date']}｜共 {report['total']} 檔","contents":{"type":"bubble","size":"mega","body":{"type":"box","layout":"vertical","paddingAll":"lg","contents":body}}}
def creds():
 token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN","").strip() or os.getenv("LINE_TOKEN","").strip();to=os.getenv("LINE_TO_ID","").strip() or os.getenv("GROUP_ID","").strip()
 if not token or not to:raise RuntimeError("F15 LINE credentials missing")
 return token,to
def send(report):
 token,to=creds();data=json.dumps({"to":to,"messages":[flex(report)],"notificationDisabled":False},ensure_ascii=False).encode();retry=str(uuid.uuid5(uuid.NAMESPACE_URL,"f15-eod-v1:"+report["date"]));req=urllib.request.Request(ENDPOINT,data=data,method="POST",headers={"Content-Type":"application/json","Authorization":"Bearer "+token,"X-Line-Retry-Key":retry})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:status=r.status;msg=r.read().decode(errors="replace")
 except urllib.error.HTTPError as e:raise RuntimeError(f"F15 LINE HTTP {e.code}: "+e.read().decode(errors="replace")[:800]) from e
 if status!=200:raise RuntimeError(f"F15 LINE status {status}: {msg[:500]}")
def reg():
 p=OUT/"sent_registry.json"
 if not p.exists():return p,{"schema":"f15_sent_v1","dates":{}}
 x=json.loads(p.read_text(encoding="utf-8"))
 if x.get("schema")!="f15_sent_v1":raise RuntimeError("F15 registry schema mismatch")
 return p,x
def process_day(day,send_line=True):
 p,r=reg()
 if day in r["dates"]:return "already_sent"
 x=build_report(day)
 if x is None:return "no_events"
 if not send_line:return x
 send(x);r["dates"][day]={"sent_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),"total":x["total"]};atomic(p,r);print(f"[F15 SENT] {day} total={x['total']} delayed={x['delayed']}",flush=True);return "sent"
def days():
 d=datetime.now(TPE).date();return [(d-timedelta(days=i)).isoformat() for i in range(7,-1,-1)]
def loop():
 OUT.mkdir(parents=True,exist_ok=True)
 while True:
  n=datetime.now(TPE);today=n.date().isoformat()
  for d in days():
   if d==today and (n.hour,n.minute)<(13,40):continue
   try:process_day(d,True)
   except BaseException as e:print(f"[F15 FAIL] {d} {type(e).__name__}: {e}",flush=True)
  time.sleep(300)
