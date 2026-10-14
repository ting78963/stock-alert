#!/usr/bin/env python3
"""Read-only B-signal subset: A discovered_at vs last completed F10 cumulative lots."""
import csv, glob, json, sqlite3, bisect
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from html import escape

BASE=Path("/var/data/stock-alert/b_live_runner_v2_p1")
DB=Path("/var/data/stock-alert/backups/pre_release_20261009_140610/f10_baseline_v1.sqlite3")
OUT=Path("/tmp/a_b_handoff_xy_v1")
def sec(t):
    try:
        d=datetime.strptime(t,"%H:%M:%S")
        return d.hour*3600+d.minute*60+d.second
    except Exception as e: raise RuntimeError("STOP bad time "+str(t)) from e
def main():
    if not BASE.is_dir() or not DB.is_file(): raise RuntimeError("STOP missing source")
    files=sorted(BASE.glob("*/*/*signal_event.json"))
    if not files: raise RuntimeError("STOP no events")
    grouped=defaultdict(set)
    for f in files:
        e=json.loads(f.read_text(encoding="utf-8"))
        day=str(e.get("date","")); sid=str(e.get("stock_id","")).zfill(4)
        t=str(e.get("discovered_at",""))
        if day!=f.parent.parent.name or sid!=f.parent.name or not t:
            raise RuntimeError("STOP event identity mismatch: "+str(f))
        sec(t)
        grouped[(day,sid)].add(t)
    for key,times in grouped.items():
        if len(times)>1: raise RuntimeError("STOP conflicting discovered_at: "+str((key,times)))
    conn=sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True)
    rows=[]; missing=[]; no_prior=[]
    for (day,sid),ts in sorted(grouped.items()):
        if not ("2026-09-29"<=day<="2026-10-08"): continue
        t=next(iter(ts))
        record=conn.execute("SELECT pts_json FROM f10_day WHERE symbol=? AND day=?",(sid,day)).fetchone()
        if record is None:
            missing.append((day,sid));continue
        pts=json.loads(record[0])
        if not pts: raise RuntimeError("STOP empty F10 "+day+" "+sid)
        last=-1; prev=-1
        for minute,v in pts:
            n=sec(minute)
            if n<=last or float(v)<prev: raise RuntimeError("STOP invalid F10 "+day+" "+sid)
            last=n;prev=float(v)
        # Minute stamp represents a full minute: only minutes strictly before handoff minute are completed.
        cutoff=(sec(t)//60)*60
        idx=bisect.bisect_left([sec(p[0]) for p in pts],cutoff)-1
        if idx<0: no_prior.append((day,sid,t));continue
        rows.append(dict(date=day,stock_id=sid,discovered_at=t,f10_last_completed_minute=pts[idx][0],cumulative_volume_zhang=float(pts[idx][1]),x_seconds=sec(t)))
    if not rows: raise RuntimeError("STOP zero matched points")
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"points.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    audit={"signal_event_files":len(files),"unique_stock_days":len(grouped),"matched_points":len(rows),"missing_f10":missing,"no_completed_minute":no_prior,"scope":"B signal events only; not all A handoffs","causality":"F10 minute < discovered_at minute"}
    (OUT/"audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    left,right,top,bottom=80,1100,55,650
    xmin,xmax=9*3600,13*3600+35*60
    ymax=max(r["cumulative_volume_zhang"] for r in rows)*1.08
    def x(t): return left+(t-xmin)/(xmax-xmin)*(right-left)
    def y(v): return bottom-v/ymax*(bottom-top)
    a=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1190 735">','<rect width="1190" height="735" fill="white"/>','<text x="80" y="30" font-family="sans-serif" font-size="21">A→B discovered_at × F10 cumulative lots (B signal subset)</text>',f'<path d="M {left} {top} V {bottom} H {right}" stroke="#333" fill="none"/>']
    for h in range(9,14):
        px=x(h*3600)
        a.append(f'<path d="M {px:.1f} {top} V {bottom}" stroke="#ddd"/><text x="{px:.1f}" y="674" font-family="sans-serif" font-size="14" text-anchor="middle">{h:02d}:00</text>')
    for i in range(6):
        v=ymax*i/5; py=y(v)
        a.append(f'<path d="M {left} {py:.1f} H {right}" stroke="#eee"/><text x="72" y="{py+5:.1f}" font-family="sans-serif" font-size="13" text-anchor="end">{v:,.0f}</text>')
    for r in rows:
        px=x(r["x_seconds"]);py=y(r["cumulative_volume_zhang"])
        title=escape(f'{r["date"]} {r["stock_id"]} {r["discovered_at"]} {r["cumulative_volume_zhang"]:.0f} lots')
        a.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="#2364aa" fill-opacity=".55"><title>{title}</title></circle>')
    a.append(f'<text x="590" y="714" font-family="sans-serif" text-anchor="middle">Handoff discovered_at (Taipei)</text><text x="16" y="355" font-family="sans-serif" transform="rotate(-90 16 355)" text-anchor="middle">Cumulative lots (張)</text><text x="1090" y="30" font-family="sans-serif" font-size="14" text-anchor="end">n={len(rows)}</text></svg>')
    (OUT/"scatter.svg").write_text("\n".join(a),encoding="utf-8")
    print("MATCHED",len(rows),"MISSING_F10",len(missing),"NO_COMPLETED_MINUTE",len(no_prior))
    print("OUTPUT",OUT/"scatter.svg",OUT/"points.csv",OUT/"audit.json")
if __name__=="__main__":main()
