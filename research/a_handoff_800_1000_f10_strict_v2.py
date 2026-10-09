#!/usr/bin/env python3
"""One-shot read-only F15 handoff replay; no production writes or API calls."""
import json, sqlite3, statistics, math
from pathlib import Path
from collections import Counter
P=Path('/var/data/stock-alert')
ROOT=P/'f15_eod/trajectory_v1'
def stop(s): raise SystemExit('AUDIT STOP: '+str(s))
def minute(s):
 try:
  h,m=map(int,str(s)[:5].split(':'))
  assert 0<=h<=23 and 0<=m<60
  return h*60+m
 except Exception: stop('bad minute '+str(s))
def num(v):
 try:
  f=float(v)
  assert math.isfinite(f) and f>=0
  return f
 except Exception: stop('invalid volume '+str(v))
def curve(raw,full,tag):
 try: pts=json.loads(raw)
 except Exception: stop('invalid F10 JSON '+tag)
 if not isinstance(pts,list) or not pts: stop('empty F10 '+tag)
 out=[]; prev_t=-1; prev_v=-1
 for pt in pts:
  if not isinstance(pt,(list,tuple)) or len(pt)!=2: stop('unexpected F10 point format '+tag)
  t=minute(pt[0]); v=num(pt[1])
  if t<=prev_t or v<prev_v: stop('invalid F10 monotonicity '+tag)
  out.append((t,v)); prev_t=t; prev_v=v
 if abs(prev_v-full)>max(0.000001,full*0.000001): stop('F10 total mismatch '+tag)
 return out
def at(pts,t):
 v=0
 for tt,vv in pts:
  if tt>t: break
  v=vv
 return v
print('F15 EARLY HANDOFF | 800 vs 1000 | READ ONLY | NO NETWORK')
fs=sorted(x for x in ROOT.glob('20??-??-??/*.json') if x.name!='manifest.json')
if not fs: stop('no F15 files')
db=sqlite3.connect('file:'+str(P/'f10_baseline_v1.sqlite3')+'?mode=ro',uri=True)
db.execute("ATTACH DATABASE 'file:"+str(P/'shared_history_stage_v1.sqlite3')+"?mode=ro' AS hist")
cal=[r[0] for r in db.execute('SELECT day FROM hist.daily_ohlcv GROUP BY day HAVING COUNT(*)>=1000 ORDER BY day')]
if len(cal)<11: stop('calendar insufficient')
records=[]; seen=set()
for file in fs:
 try:
  d=json.loads(file.read_text()); i=d['identity']
  day=str(i['date']); sym=str(i['stock_id']); cls=str(i['signal_class'])
  rec=minute(i['recognition_time']); rows=d['trajectory_raw_1m']
 except Exception as e: stop('invalid F15 '+str(file)+' '+str(e))
 ident=(day,sym,cls,rec)
 if day!=file.parent.name or cls not in ('A','B','C','P1') or ident in seen or not rows: stop('identity mismatch '+str(file))
 seen.add(ident); obs=[]; lt=-1; lv=-1
 for row in rows:
  t=minute(row['minute']); v=num(row['cum_volume'])
  if t<=lt or v<lv: stop('nonmonotonic F15 '+str(file))
  lt=t; lv=v
  if t<rec: obs.append((t,v))
 records.append((ident,obs))
print('IDENTITY PASS:',len(records),dict(Counter(x[0][2] for x in records)))
out=[]; excluded=[]
for (day,sym,cls,rec),obs in records:
 prev=[d for d in cal if d<day][-10:]
 if len(prev)!=10:
  excluded.append((day,sym,cls,'calendar')); continue
 q=','.join('?' for _ in prev)
 got={}
 for d,full,raw in db.execute('SELECT day,full,pts_json FROM f10_day WHERE symbol=? AND day IN ('+q+')',(sym,*prev)):
  f=num(full)
  if f<=0: stop('nonpositive F10 total '+sym+' '+d)
  got[d]=(f,curve(raw,f,sym+' '+d))
 missing=[d for d in prev if d not in got]
 if missing:
  excluded.append((day,sym,cls,'missing '+','.join(missing))); continue
 ten=[got[d] for d in prev]; avg5=sum(x[0] for x in ten[-5:])/5; prev1=ten[-1][0]
 first={800:None,1000:None}
 for t,v in obs:
  f10=sum(at(pts,t)/full for full,pts in ten)/10
  if f10<=0: continue
  projected=v/f10
  if projected/avg5<2.5 and (projected/prev1-1)*100<150: continue
  for th in first:
   if first[th] is None and v>=th: first[th]=t
 out.append((day,sym,cls,rec,first))
print('ELIGIBLE',len(out),'EXCLUDED',len(excluded))
print('EXCLUDED BY DAY',dict(sorted(Counter(x[0] for x in excluded).items())))
print('EXCLUDED BY CLASS',dict(Counter(x[2] for x in excluded)))
for th in (800,1000):
 print('THRESHOLD',th)
 for group in ('ABC','P1'):
  a=[x for x in out if (x[2]!='P1')==(group=='ABC')]
  leads=[x[3]-x[4][th] for x in a if x[4][th] is not None]
  print(group,'eligible',len(a),'early',len(leads),'median_lead',statistics.median(leads) if leads else 'N/A')
print('LIMIT: no all-market B workload from F15 signals only.')
print('LIMIT: excluded rows are not threshold failures.')
db.close()
