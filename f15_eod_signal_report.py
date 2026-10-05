# -*- coding: utf-8 -*-
"""F15 EOD archive + approved LINE Flex renderer. Presentation only; no recognition changes."""
from __future__ import annotations
import json,os,runpy,time,urllib.request,urllib.error,uuid
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path(__file__).resolve().parent;STATE=Path(os.environ.get("PRODUCTION_STATE_DIR",str(BASE/"_production_output")));EVENTS=STATE/"b_live_runner_v2_p1";OUT=STATE/"f15_eod";ENGINE=BASE/"fugle_b_engine_v2_p1.py"
TPE=ZoneInfo("Asia/Taipei");ORDER=("P1","A","B","C");ENDPOINT="https://api.line.me/v2/bot/message/push";RED="#B4232C";DARK="#A71924";TEXT="#1F2328";MUTED="#9298A2";BORDER="#E8EAED";WHITE="#FFFFFF";SOFT="#F5F6F8";DELAY="#FDE9EB"
def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+".tmp");q.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8");q.replace(p)
def normt(s):s=str(s or "").strip();return s[:5] if len(s)>=5 else s
def secs(s):p=normt(s).split(":");return int(p[0])*3600+int(p[1])*60
def pc(x):return f"{float(x):+.2f}%"
def dtxt(x):
 if x<=0:return "—"
 m,s=divmod(int(x),60);return f"+{m}m" if not s else f"+{m}m{s:02d}s"
def tx(s,size="xs",color=TEXT,weight=None,align=None,flex=None,wrap=False):
 x={"type":"text","text":str(s),"size":size,"color":color}
 if weight in ("bold","regular"):x["weight"]=weight
 if align in ("start","center","end"):x["align"]=align
 if flex is not None:x["flex"]=int(flex)
 if wrap:x["wrap"]=True
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
  if rec in bt:rp=float(bt[rec]["close"]);src=rec
  elif str(e.get("signal_class","")).upper() in ("A","B","C") and e.get("frozen_early_price") is not None:rp=float(e["frozen_early_price"]);src="event:frozen_early_price"
  else:raise RuntimeError(f"F15 missing recognition price {day} {sid} {rec}")
  _,prev,_=M["fetch_prev"](key,sid,day);close=float(bars[-1]["close"]);delay=max(0,secs(e["discovered_at"])-secs(rec)) if e.get("late_discovery") is True else 0
  rows.append({"date":day,"stock_id":sid,"stock_name":str(e.get("stock_name") or sid),"signal_class":str(e["signal_class"]).upper(),"recognition_time":rec,"recognition_price":rp,"recognition_price_source":src,"prior_close":prev,"recognition_gain_pct":(rp/prev-1)*100,"discovered_at":e["discovered_at"],"delay_seconds":delay,"close_price":close,"close_gain_pct":(close/prev-1)*100,"source":"Fugle historical 1m + production event"})
 rows.sort(key=lambda r:(ORDER.index(r["signal_class"]),r["recognition_time"],r["stock_id"]));counts={c:sum(r["signal_class"]==c for r in rows) for c in ORDER};x={"schema":"f15_eod_v1","date":day,"generated_at_taipei":datetime.now(TPE).isoformat(timespec="seconds"),"counts":counts,"total":len(rows),"delayed":sum(r["delay_seconds"]>0 for r in rows),"limit_up_like":sum(r["close_gain_pct"]>=9.5 for r in rows),"rows":rows};atomic(OUT/f"{day}.json",x);return x
def row(r):
 left={"type":"box","layout":"vertical","flex":12,"contents":[tx(r["stock_name"],"sm",TEXT,"bold"),tx(r["stock_id"],"xxs",MUTED)]}
 midc=[tx(r["recognition_time"],"sm",TEXT)]
 if r["delay_seconds"]>0:midc.append({"type":"box","layout":"vertical","backgroundColor":DELAY,"cornerRadius":"sm","paddingAll":"xs","margin":"xs","contents":[tx(dtxt(r["delay_seconds"]),"xxs",RED,"bold","center")]})
 else:midc.append(tx("—","xxs",MUTED))
 mid={"type":"box","layout":"vertical","flex":9,"contents":midc};right={"type":"box","layout":"vertical","flex":11,"alignItems":"flex-end","contents":[tx(pc(r["recognition_gain_pct"]),"sm",RED),tx(pc(r["close_gain_pct"]),"sm",RED,"bold")]}
 return {"type":"box","layout":"horizontal","alignItems":"center","paddingTop":"sm","paddingBottom":"sm","contents":[left,mid,right]}
def section(c,rr):
 z=[{"type":"box","layout":"horizontal","alignItems":"center","margin":"lg","contents":[tx(c,"xl",RED,"bold",flex=0),{"type":"separator","margin":"md","color":RED},{"type":"text","text":f"共 {len(rr)} 檔","size":"sm","weight":"bold","color":RED,"margin":"md","flex":0}]},{"type":"box","layout":"horizontal","backgroundColor":SOFT,"paddingAll":"sm","contents":[tx("股票 / 代號","xxs",MUTED,flex=12),tx("辨識 / 延遲","xxs",MUTED,flex=9),tx("漲幅 / 收盤","xxs",MUTED,align="end",flex=11)]}]
 for i,r in enumerate(rr):
  z.append(row(r))
  if i<len(rr)-1:z.append({"type":"separator","color":BORDER})
 return {"type":"box","layout":"vertical","contents":z}
def _summary(report):
 c=report["counts"]
 return [{"type":"separator","color":BORDER,"margin":"xl"},{"type":"box","layout":"horizontal","margin":"md","contents":[tx(f"P1 {c['P1']}｜A {c['A']}｜B {c['B']}｜C {c['C']}","xs",RED,"bold",flex=1),tx(f"總計 {report['total']} 檔","xs",TEXT,"bold","end",1)]},{"type":"box","layout":"horizontal","margin":"sm","contents":[tx(f"◷ A延遲 {report['delayed']} 檔","xs",MUTED,flex=1),tx(f"★ 漲停 {report['limit_up_like']} 檔","xs",RED,"bold","end",1)]},{"type":"box","layout":"vertical","backgroundColor":DARK,"cornerRadius":"lg","paddingAll":"md","margin":"lg","contents":[tx("▲   盤後訊號統計","md",WHITE,"bold","center")]},tx("歷史統計・僅供參考     Trade Smart | Your Edge","xxs",MUTED,"regular","center")]
def _bubble(report,groups,part=1,parts=1):
 head=[{"type":"box","layout":"horizontal","alignItems":"center","contents":[tx("↗ BUY SIGNAL","sm",RED,"bold",flex=1),tx("盤後訊號統計"+(f" {part}/{parts}" if parts>1 else ""),"xs",MUTED,"regular","end",1)]},tx(report["date"].replace("-"," / "),"xxl",TEXT,"bold"),{"type":"separator","color":BORDER,"margin":"lg"}]
 for c,rr in groups:
  if rr:head.append(section(c,rr))
 if part==parts:head.extend(_summary(report))
 return {"type":"bubble","size":"mega","body":{"type":"box","layout":"vertical","paddingAll":"xl","contents":head}}
def flex_messages(report):
 # Keep approved screenshot renderer. If one bubble exceeds LINE's 30KB bubble limit,
 # split only at class/row boundaries; visual grammar remains identical.
 groups=[(c,[r for r in report["rows"] if r["signal_class"]==c]) for c in ORDER];groups=[g for g in groups if g[1]]
 one=_bubble(report,groups)
 if len(json.dumps(one,ensure_ascii=False,separators=(",",":")).encode())<29500:return [{"type":"flex","altText":f"盤後訊號統計｜{report['date']}｜共 {report['total']} 檔","contents":one}]
 # Greedy row chunks, preserving class order. Conservative cap leaves room for footer.
 chunks=[];cur=[]
 for c,rr in groups:
  for r in rr:
   trial=cur+[(c,[r])]
   # merge adjacent same-class fragments before sizing
   merged=[]
   for cc,rs in trial:
    if merged and merged[-1][0]==cc:merged[-1][1].extend(rs)
    else:merged.append((cc,list(rs)))
   if cur and len(json.dumps(_bubble(report,merged,1,2),ensure_ascii=False,separators=(",",":")).encode())>23500:
    chunks.append(cur);cur=[(c,[r])]
   else:cur=merged
 if cur:chunks.append(cur)
 out=[];n=len(chunks)
 for i,g in enumerate(chunks,1):
  b=_bubble(report,g,i,n)
  if len(json.dumps(b,ensure_ascii=False,separators=(",",":")).encode())>=30000:raise RuntimeError(f"F15 renderer bubble >=30KB {report['date']} part={i}")
  out.append({"type":"flex","altText":f"盤後訊號統計｜{report['date']}｜{i}/{n}","contents":b})
 return out
def flex(report):return flex_messages(report)[0]
def creds():
 token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN","").strip() or os.getenv("LINE_TOKEN","").strip();to=os.getenv("LINE_TO_ID","").strip() or os.getenv("GROUP_ID","").strip()
 if not token or not to:raise RuntimeError("F15 LINE credentials missing")
 return token,to
def send(report,retry_scope="daily"):
 token,to=creds();msgs=flex_messages(report)
 for i,msg in enumerate(msgs,1):
  data=json.dumps({"to":to,"messages":[msg],"notificationDisabled":False},ensure_ascii=False,separators=(",",":")).encode();retry=str(uuid.uuid5(uuid.NAMESPACE_URL,f"f15-{retry_scope}:{report['date']}:{i}"));req=urllib.request.Request(ENDPOINT,data=data,method="POST",headers={"Content-Type":"application/json","Authorization":"Bearer "+token,"X-Line-Retry-Key":retry})
  try:
   with urllib.request.urlopen(req,timeout=20) as r:status=r.status;msgbody=r.read().decode(errors="replace")
  except urllib.error.HTTPError as e:raise RuntimeError(f"F15 LINE HTTP {e.code}: "+e.read().decode(errors="replace")[:800]) from e
  if status!=200:raise RuntimeError(f"F15 LINE status {status}: {msgbody[:500]}")
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
