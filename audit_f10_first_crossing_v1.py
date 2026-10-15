#!/usr/bin/env python3
"""Read-only F10 crossing audit. Does not modify production or call network."""
import csv,json,sqlite3,datetime as dt,collections,statistics,sys
from pathlib import Path
CSV=Path("/tmp/a_b_handoff_xy_v1/points.csv")
DB=Path("/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3")
LEVELS=(800,1000,1500,2000,3000,4000,10000)
def stop(msg): raise SystemExit("STOP / FAIL CLOSED: "+msg)
if not CSV.is_file() or not DB.is_file(): stop("Missing input "+str((CSV,DB)))
rows=list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
if len(rows)!=182: stop(f"Expected 182 rows, found {len(rows)}")
if len({(r["date"],r["stock_id"]) for r in rows})!=len(rows): stop("Duplicate stock-day")
con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
schema={r[1] for r in con.execute("PRAGMA table_info(f10_day)")}
if not {"symbol","day","pts_json"}.issubset(schema): stop(f"Bad F10 schema {schema}")
def minute(s):
    s=str(s)
    # Supported timestamp forms: HH:MM[:SS], YYYY-MM-DD HH:MM[:SS], ISO datetime
    if "T" in s: s=s.split("T")[-1]
    if " " in s: s=s.split(" ")[-1]
    s=s[:5]
    try:
        t=dt.datetime.strptime(s,"%H:%M")
        return t.hour*60+t.minute
    except ValueError: stop("Unrecognized timestamp "+str(s))
def parse_pts(raw):
    a=json.loads(raw)
    if not isinstance(a,list) or not a: stop("Empty/non-list pts_json")
    out=[]
    for p in a:
        if isinstance(p,(list,tuple)) and len(p)>=2: t,v=p[0],p[1]
        elif isinstance(p,dict):
            t=next((p[k] for k in ("minute","time","t","timestamp") if k in p),None)
            v=next((p[k] for k in ("cumulative_volume_zhang","cum","volume","v") if k in p),None)
        else: stop("Unsupported F10 point "+repr(p)[:120])
        if t is None or v is None: stop("Missing F10 time/volume")
        out.append((minute(t),float(v)))
    if any(out[i][0]>=out[i+1][0] for i in range(len(out)-1)): stop("F10 minutes not strictly increasing")
    if any(out[i][1]>out[i+1][1]+1e-8 for i in range(len(out)-1)): stop("F10 cumulative volume decreased")
    return out
summary=collections.defaultdict(list)
out=[]
missing=[]
for r in rows:
    d,s=r["date"],r["stock_id"]
    q=con.execute("SELECT pts_json FROM f10_day WHERE symbol=? AND day=?",(s,d)).fetchall()
    if len(q)!=1: missing.append((d,s,len(q)));continue
    pts=parse_pts(q[0][0])
    hand=minute(r["discovered_at"])
    prev=[(t,v) for t,v in pts if t<hand]
    if not prev: stop(f"No completed minute {d} {s}")
    observed=float(r["cumulative_volume_zhang"])
    if abs(prev[-1][1]-observed)>0.05: stop(f"Volume mismatch {d} {s}: CSV={observed}, F10={prev[-1][1]}")
    item={"date":d,"stock_id":s,"handoff":r["discovered_at"],"handoff_volume":observed}
    for lv in LEVELS:
        reached=next((t for t,v in prev if v>=lv),None)
        item[f"first_{lv}"]=f"{reached//60:02d}:{reached%60:02d}" if reached is not None else ""
        item[f"wait_{lv}_min"]=hand-reached if reached is not None else ""
        if reached is not None: summary[lv].append(hand-reached)
    out.append(item)
print("AUDIT input_rows",len(rows),"matched",len(out),"missing",missing)
if missing: stop("Missing F10 stock-days; no downstream interpretation")
print("LEVEL | REACHED_BY_HANDOFF | WAIT_MEDIAN_MIN | WAIT_P90_MIN | WAIT_MAX_MIN | WAIT_OVER_30MIN")
for lv in LEVELS:
    v=sorted(summary[lv]); n=len(v)
    print(lv,n,round(statistics.median(v),1) if n else "-",v[min(n-1,int(.9*(n-1)))] if n else "-",max(v) if n else "-",sum(x>30 for x in v))
print("\\nLONGEST WAIT AFTER 2000 LOTS (only stocks that reached 2000 before handoff)")
z=sorted((x for x in out if x["wait_2000_min"]!=""),key=lambda x:x["wait_2000_min"],reverse=True)
for x in z[:20]:
    print(x["date"],x["stock_id"],"first2000",x["first_2000"],"handoff",x["handoff"],"wait_min",x["wait_2000_min"],"handoff_volume",x["handoff_volume"])
print("\\nIMPORTANT: F10 minute timestamps are treated as completed-minute observations; wait times are minute-resolution, not proof of A system delay.")
