from __future__ import annotations
import numpy as np
import pandas as pd
from attack_engine import find_attacks,compute_c_values,fill_entry_prices

EPS=1e-12; SEG=5.0
STATE595="UPWARD_DISPLACEMENT_PRESENT"; STATE70="UPWARD_REGEN_BELOW_OR_AT_A2"

def norm_time(x):
    if x is None or pd.isna(x):return ""
    s=str(x).strip()
    if " " in s:s=s.split()[-1]
    if len(s)==5:s+=":00"
    return s[:8]

def clock_minute(x):
    try:
        h,m,s=norm_time(x).split(":"); return int(h)*60+int(m)+float(s)/60
    except:return np.nan

def fmt_clock(m):
    if not np.isfinite(m):return ""
    h=int(m//60); mi=int(round(m-h*60))
    if mi>=60:h+=1;mi-=60
    return f"{h:02d}:{mi:02d}:00"

def bars_df(items,fallback_date,sid):
    rows=[{"date":str(b.get("date") or fallback_date),"stock_id":str(b.get("stock_id") or sid).zfill(4),
           "time_str":norm_time(b.get("minute") or b.get("time")),"open":b.get("open"),"high":b.get("high"),
           "low":b.get("low"),"close":b.get("close"),"volume":b.get("volume")} for b in (items or [])]
    d=pd.DataFrame(rows)
    if d.empty:return d
    for c in ["open","high","low","close","volume"]:d[c]=pd.to_numeric(d[c],errors="coerce")
    d["time"]=d["time_str"]; d["minute_abs"]=d["time_str"].map(clock_minute)
    return d.dropna(subset=["minute_abs","open","high","low","close","volume"]).sort_values("minute_abs",kind="stable").reset_index(drop=True)

def reconstruct_a2(d,prev_close,prev_day_volume):
    early=d[(d.time_str>="09:00:00")&(d.time_str<="09:10:00")]
    if early.empty:return {"attack_count":0,"v1_pass":False,"v1_reason":"NO_EARLY_BARS"}
    key=float(early.high.max()); eh=(key/prev_close-1)*100
    attacks=fill_entry_prices(compute_c_values(find_attacks(d.copy(),key,"09:10:00",search_end="13:30:00")),d)
    rec={"key_price":key,"early_high_pct":eh,"attack_count":len(attacks),"v1_pass":False,"v1_reason":""}
    if len(attacks)<2:return rec
    a1,a2=attacks[0],attacks[1]
    a1e=norm_time(a1.get("end_time")); a2s=norm_time(a2.get("start_time")); a2e=norm_time(a2.get("end_time"))
    dd=d.copy(); dd["cum_vol"]=dd.volume.clip(lower=0).cumsum(); q=dd[dd.time_str<=a2e]
    vr=float(q.iloc[-1].cum_vol)/prev_day_volume if len(q) else np.nan
    rec.update({"a1_end":a1e,"a2_start":a2s,"a2_end":a2e,"a2_vr":vr,"a2_upward":bool(a2.get("is_upward"))})
    return rec

def candidate_type(vr,eh):
    if not np.isfinite(vr) or not np.isfinite(eh):return "NO_BUY"
    if vr<.5 and 3<=eh<5:return "A"
    if vr<.5 and 5<=eh<6:return "B"
    if vr>=.5 and 5<=eh<6:return "C"
    return "NO_BUY"

def state_at(d,a2_abs,endpoint):
    pre=d[d.minute_abs<=a2_abs+EPS]
    if pre.empty:return None
    base=float(pre.iloc[-1].close); path=d[(d.minute_abs>a2_abs+EPS)&(d.minute_abs<=endpoint+EPS)]
    cur=base if path.empty else float(path.iloc[-1].close); high=base if path.empty else float(path.high.max())
    return base,cur,(cur/base-1)*100,(high/base-1)*100

def replay_early(d,a2_end):
    a2=clock_minute(a2_end)
    if not np.isfinite(a2):return {"early_status":"DATA_INCOMPLETE","early_reason":"BAD_A2_CLOCK"}
    max_obs=float(d.minute_abs.max()); prevD=prevM=0.0
    direction=generation=frontier=recurrence=False; seen_gen=pause=False; rows=[]; endpoint=a2+SEG
    while endpoint<=min(810.0,max_obs)+EPS:
        st=state_at(d,a2,endpoint)
        if st is None:break
        base,cur,D,MFE=st; raw_gen=D-prevD>EPS; raw_front=MFE>prevM+EPS
        direction=direction or D>0; generation=generation or raw_gen; frontier=frontier or raw_front
        re=False
        if raw_gen:
            if seen_gen and pause:re=True
            seen_gen=True; pause=False
        elif seen_gen:pause=True
        recurrence=recurrence or re
        rows.append({"endpoint_abs":endpoint,"D_current_pct":D,"MFE_sofar_pct":MFE,
                     "raw_generation_event":raw_gen,"raw_frontier_event":raw_front,
                     "direction_seen":direction,"generation_seen":generation,"frontier_seen":frontier,
                     "recurrence_event":re,"recurrence_seen":recurrence})
        if direction and generation and frontier and recurrence:
            return {"early_status":"EARLY","early_time":fmt_clock(endpoint),"early_abs":endpoint,
                    "early_elapsed_min":endpoint-a2,"early_price":cur,"early_D_from_A2_pct":D,
                    "early_MFE_from_A2_pct":MFE,"physical_state":STATE595 if D>0 else STATE70,"path_rows":rows}
        prevD,prevM=D,MFE; endpoint+=SEG
    return {"early_status":"NO_EARLY","early_reason":"not_reached_by_last_completed_observation","path_rows":rows}
