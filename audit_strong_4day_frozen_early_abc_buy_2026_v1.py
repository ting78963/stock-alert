# -*- coding: utf-8 -*-
r"""
2026-09-18 | FROZEN V1 -> FROZEN EARLY | OUT-OF-V1 FROZEN EARLY GENERALIZATION v1

Purpose
-------
Use stock_snapshot_2026-09-18.json "passed" ONLY as the stock roster.
Strong timing / final Strong values are NOT used by V1 or Early recognition.

For each stock:
1) Reconstruct Frozen V1 with the original local attack_engine.
2) If V1 passes, replay the Frozen Early process causally from A2 in fixed 5-minute
   completed observations.
3) Freeze the FIRST Early recognition minute and price.
4) ONLY AFTER Early is frozen, open the rest of D0 to report:
   - Early gain vs previous close
   - today's maximum gain vs previous close
   - Early -> today's high gap in percentage points
   - actual price return from Early price to post-Early high
   - close gain vs previous close
   - whether price later fell below Early price
   - first breach time and post-Early MAE

Frozen V1
---------
Key = max high from 09:00 through 09:10 inclusive.
A1/A2 = original backend.events.attack_engine attacks after 09:10.
V1 requires:
  3 <= EarlyHigh < 5
  A2 end < 09:30
  A2 Upward
  cumulative volume through A2 end / previous-day full-day volume < 0.5

Frozen Early
------------
Same causal process-property definition already frozen:
  Direction seen   : D > 0 has been observed
  Generation seen  : positive raw delta-D has been observed
  Frontier seen    : positive MFE extension has been observed
  Recurrence seen  : generation -> at least one non-generation observation -> generation
  EARLY = first completed 5-minute observation where
          Direction + Generation + Frontier + Recurrence are all historical facts.

No Formation / no future outcome / no Strong timing enters recognition.

Expected runtime: ~2-15 sec.
Main bottleneck: importing the original attack_engine and replaying minute bars for the roster.
Original data are READ ONLY. Output only under _research_output.
"""

from pathlib import Path
import importlib
import json
import sys
import numpy as np
import pandas as pd

HOME = Path.home()
BASE = HOME / "Desktop" / "新增資料夾"
PROJECT = HOME / "Desktop" / "taiwan-backtest-v9-final" / "taiwan-backtest-v9-final" / "tb-pkg"
SNAP = BASE / "stock_snapshot_2026-09-18.json"
OUT = BASE / "_research_output" / "frozen_early_generalization_replay_20260918_v1"
OUT.mkdir(parents=True, exist_ok=True)

EPS = 1e-12
SEG = 5.0
STATE595 = "UPWARD_DISPLACEMENT_PRESENT"
STATE70 = "UPWARD_REGEN_BELOW_OR_AT_A2"

def stop(msg):
    print("\n" + "="*180)
    print("AUDIT FAILED -> STOP -> NO RESEARCH INTERPRETATION")
    print("="*180)
    print(msg)
    raise SystemExit(2)

def norm_time(x):
    if x is None or pd.isna(x):
        return ""
    s = str(x).strip()
    if " " in s:
        s = s.split()[-1]
    if len(s) == 5:
        s += ":00"
    return s[:8]

def clock_minute(x):
    s = norm_time(x)
    try:
        h, m, sec = s.split(":")
        return int(h)*60 + int(m) + float(sec)/60.0
    except Exception:
        return np.nan

def fmt_clock(m):
    if not np.isfinite(m):
        return ""
    h = int(m // 60)
    mi = int(round(m - h*60))
    if mi >= 60:
        h += 1; mi -= 60
    return f"{h:02d}:{mi:02d}:00"

def bars_df(items, fallback_date, sid):
    rows=[]
    for b in items or []:
        rows.append({
            "date": str(b.get("date") or fallback_date),
            "stock_id": str(b.get("stock_id") or sid).zfill(4),
            "time_str": norm_time(b.get("minute") or b.get("time")),
            "open": b.get("open"), "high": b.get("high"), "low": b.get("low"),
            "close": b.get("close"), "volume": b.get("volume"),
        })
    d=pd.DataFrame(rows)
    if d.empty:
        return d
    for c in ["open","high","low","close","volume"]:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    # Original attack_engine requires a literal "time" column.
    # Keep time_str for this replay's comparisons, and expose the same
    # normalized causal minute as "time" for the original frozen engine.
    d["time"] = d["time_str"]
    d["minute_abs"]=d["time_str"].map(clock_minute)
    d=d.dropna(subset=["minute_abs","open","high","low","close","volume"])
    return d.sort_values("minute_abs",kind="stable").reset_index(drop=True)

def load_engine():
    if not PROJECT.exists():
        stop(f"Original project missing: {PROJECT}")
    sys.path.insert(0,str(PROJECT))
    try:
        ae=importlib.import_module("backend.events.attack_engine")
        return ae.find_attacks, ae.compute_c_values, ae.fill_entry_prices
    except Exception as e:
        stop(f"Cannot import original attack_engine: {e}")

def previous_context(s,date,sid):
    y=bars_df(s.get("kbar_yesterday"),date,sid)
    if y.empty:
        return None
    pc=float(y.iloc[-1].close)
    pv=float(y.volume.clip(lower=0).sum())
    if not np.isfinite(pc) or pc<=0 or not np.isfinite(pv) or pv<=0:
        return None
    return pc,pv

def reconstruct_a2(d,prev_close,prev_day_volume,find_attacks,compute_c_values,fill_entry_prices):
    early=d[(d.time_str>="09:00:00")&(d.time_str<="09:10:00")]
    if early.empty:
        return {
            "v1_pass":False,"v1_reason":"NO_EARLY_BARS",
            "cond_earlyhigh_3_to_lt5":False,
            "cond_a2_before_0930":False,
            "cond_a2_upward":False,
            "cond_a2_vr_lt_0_5":False,
            "would_pass_v1_without_earlyhigh_limit":False,
            "only_earlyhigh_block":False,
            "earlyhigh_block_side":""
        }

    key=float(early.high.max())
    early_high=(key/prev_close-1)*100

    attacks=find_attacks(d.copy(),key,"09:10:00",search_end="13:30:00")
    attacks=compute_c_values(attacks)
    attacks=fill_entry_prices(attacks,d)

    rec={"key_price":key,"early_high_pct":early_high,
         "attack_count":len(attacks),"v1_pass":False,"v1_reason":""}
    if len(attacks)<2:
        rec["v1_reason"]=f"attack_count={len(attacks)} < 2"
        rec.update({
            "cond_earlyhigh_3_to_lt5": bool(3.0 <= early_high < 5.0),
            "cond_a2_before_0930": False,
            "cond_a2_upward": False,
            "cond_a2_vr_lt_0_5": False,
            "would_pass_v1_without_earlyhigh_limit": False,
            "only_earlyhigh_block": False,
            "earlyhigh_block_side": ""
        })
        return rec

    a1,a2=attacks[0],attacks[1]
    a1_end=norm_time(a1.get("end_time"))
    a2_start=norm_time(a2.get("start_time"))
    a2_end=norm_time(a2.get("end_time"))
    a2_up=bool(a2.get("is_upward"))

    dd=d.copy()
    dd["cum_vol"]=dd.volume.clip(lower=0).cumsum()
    q=dd[dd.time_str<=a2_end]
    a2_vr=float(q.iloc[-1].cum_vol)/prev_day_volume if len(q) else np.nan

    cond_early=3.0<=early_high<5.0
    cond_time=("09:00:00"<=a2_end<"09:30:00")
    cond_up=a2_up
    cond_vr=np.isfinite(a2_vr) and a2_vr<0.5
    passed=bool(cond_early and cond_time and cond_up and cond_vr)

    reasons=[]
    if not cond_early: reasons.append("EarlyHigh_not_3_to_lt5")
    if not cond_time: reasons.append("A2_not_before_0930")
    if not cond_up: reasons.append("A2_not_upward")
    if not cond_vr: reasons.append("A2_VR_not_lt0.5")

    rec.update({
        "a1_end":a1_end,"a2_start":a2_start,"a2_end":a2_end,
        "a2_vr":a2_vr,"a2_upward":a2_up,
        "v1_pass":passed,"v1_reason":"" if passed else ";".join(reasons)
    })
    # Diagnostic-only decomposition. This does NOT alter Frozen V1.
    rec["cond_earlyhigh_3_to_lt5"] = bool(cond_early)
    rec["cond_a2_before_0930"] = bool(cond_time)
    rec["cond_a2_upward"] = bool(cond_up)
    rec["cond_a2_vr_lt_0_5"] = bool(cond_vr)
    rec["would_pass_v1_without_earlyhigh_limit"] = bool(cond_time and cond_up and cond_vr)
    rec["only_earlyhigh_block"] = bool((not cond_early) and cond_time and cond_up and cond_vr)
    if rec["only_earlyhigh_block"]:
        rec["earlyhigh_block_side"] = "LOW_LT3" if early_high < 3.0 else "HIGH_GE5"
    else:
        rec["earlyhigh_block_side"] = ""
    return rec

def state_at(d,a2_abs,endpoint):
    pre=d[d.minute_abs<=a2_abs+EPS]
    if pre.empty:
        return None
    base=float(pre.iloc[-1].close)
    path=d[(d.minute_abs>a2_abs+EPS)&(d.minute_abs<=endpoint+EPS)]
    if path.empty:
        cur=base; high=base
    else:
        cur=float(path.iloc[-1].close)
        high=float(path.high.max())
    D=(cur/base-1)*100
    MFE=(high/base-1)*100
    return base,cur,D,MFE

def replay_early(d,a2_end):
    """
    Causal completed-observation replay.
    No row after endpoint enters the state at that endpoint.
    """
    a2_abs=clock_minute(a2_end)
    if not np.isfinite(a2_abs):
        return {"early_status":"DATA_INCOMPLETE","early_reason":"BAD_A2_CLOCK"}

    max_obs=float(d.minute_abs.max())
    prev_D=0.0
    prev_MFE=0.0

    direction_seen=False
    generation_seen=False
    frontier_seen=False
    recurrence_seen=False

    seen_gen=False
    pause_since_gen=False

    rows=[]
    endpoint=a2_abs+SEG
    while endpoint<=min(810.0,max_obs)+EPS:
        st=state_at(d,a2_abs,endpoint)
        if st is None:
            break
        a2_close,cur,D,MFE=st

        raw_gen=bool(D-prev_D>EPS)
        raw_frontier=bool(MFE>prev_MFE+EPS)

        direction_seen = direction_seen or (D>0)
        generation_seen = generation_seen or raw_gen
        frontier_seen = frontier_seen or raw_frontier

        recurrence_event=False
        if raw_gen:
            if seen_gen and pause_since_gen:
                recurrence_event=True
            seen_gen=True
            pause_since_gen=False
        else:
            if seen_gen:
                pause_since_gen=True
        recurrence_seen = recurrence_seen or recurrence_event

        recurrent_body=direction_seen and generation_seen and frontier_seen and recurrence_seen

        rows.append({
            "endpoint_abs":endpoint,
            "minutes_since_a2_end":endpoint-a2_abs,
            "current_close":cur,"D_current_pct":D,"MFE_sofar_pct":MFE,
            "raw_generation_event":raw_gen,"raw_frontier_event":raw_frontier,
            "direction_seen":direction_seen,"generation_seen":generation_seen,
            "frontier_seen":frontier_seen,"recurrence_event":recurrence_event,
            "recurrence_seen":recurrence_seen,"early_now":recurrent_body
        })

        if recurrent_body:
            return {
                "early_status":"EARLY",
                "early_time":fmt_clock(endpoint),
                "early_abs":endpoint,
                "early_elapsed_min":endpoint-a2_abs,
                "early_price":cur,
                "early_D_from_A2_pct":D,
                "early_MFE_from_A2_pct":MFE,
                "physical_state":STATE595 if D>0 else STATE70,
                "path_rows":rows
            }

        prev_D,prev_MFE=D,MFE
        endpoint+=SEG

    return {"early_status":"NO_EARLY","early_reason":"not_reached_by_last_completed_observation",
            "path_rows":rows}

def post_early_metrics(d,prev_close,early_abs,early_price):
    # Future is opened ONLY here, after Early has already been frozen.
    # Execution semantics: the Early bar is only known after it completes,
    # so post-Early metrics start strictly AFTER that completed bar.
    post=d[d.minute_abs>early_abs+EPS].copy()
    if post.empty:
        return {}

    day_high=float(d.high.max())
    day_high_gain=(day_high/prev_close-1)*100

    post_high=float(post.high.max())
    high_rows=post[np.isclose(post.high,post_high,rtol=0,atol=1e-12)]
    post_high_time=str(high_rows.iloc[0].time_str) if len(high_rows) else ""

    early_gain=(early_price/prev_close-1)*100
    gap_pp=day_high_gain-early_gain
    actual_ret=(post_high/early_price-1)*100

    close_price=float(d.iloc[-1].close)
    close_gain=(close_price/prev_close-1)*100
    close_vs_early=(close_price/early_price-1)*100

    # A minute is a breach if its LOW is below Early price.
    breach=post[post.low < early_price-EPS]
    breached=not breach.empty
    first_breach=str(breach.iloc[0].time_str) if breached else ""

    post_low=float(post.low.min())
    mae=(post_low/early_price-1)*100

    return {
        "early_gain_vs_prev_pct":early_gain,
        "today_high_price":day_high,
        "today_high_gain_vs_prev_pct":day_high_gain,
        "post_early_high_price":post_high,
        "post_early_high_time":post_high_time,
        "early_to_high_gap_pp":gap_pp,
        "early_to_high_actual_return_pct":actual_ret,
        "close_price":close_price,
        "close_gain_vs_prev_pct":close_gain,
        "close_vs_early_return_pct":close_vs_early,
        "fell_below_early":breached,
        "first_below_early_time":first_breach,
        "post_early_low_price":post_low,
        "post_early_mae_pct":mae,
    }



def next_minute_entry(d, early_abs):
    """Strictly first observed market minute AFTER completed Early recognition."""
    z=d[d.minute_abs > float(early_abs)+EPS].sort_values("minute_abs",kind="stable")
    if z.empty:
        return np.nan, "", np.nan
    r=z.iloc[0]
    return float(r.open), str(r.time_str), float(r.minute_abs)

def choose_snapshot(date, preferred_name):
    preferred=BASE/preferred_name
    if preferred.exists():
        return preferred
    hits=sorted(BASE.glob(f"stock_snapshot_{date}*.json"))
    if len(hits)==1:
        return hits[0]
    if len(hits)==0:
        stop(f"{date}: snapshot not found. Expected {preferred}")
    stop(f"{date}: ambiguous snapshots ({len(hits)}). Put the newly supplied file at: {preferred}")

def candidate_type(a2_vr, eh):
    if not np.isfinite(a2_vr) or not np.isfinite(eh):
        return "NO_BUY"
    if a2_vr < 0.5 and 3.0 <= eh < 5.0:
        return "A_LOWVR_EH3_LT5"
    if a2_vr < 0.5 and 5.0 <= eh < 6.0:
        return "B_LOWVR_EH5_LT6"
    if a2_vr >= 0.5 and 5.0 <= eh < 6.0:
        return "C_HIGHVR_EH5_LT6"
    return "NO_BUY"

def main():
    print("="*200)
    print("STRONG 2026-09-15..18 | FROZEN EARLY BUY CANDIDATES A/B/C | CAUSAL AUDITOR v1")
    print("="*200)
    print("Strong snapshot = external roster/final-value comparison ONLY.")
    print("Recognition uses original attack_engine + Frozen Early causal replay.")
    print("A = VR<0.5 & EH 3-<5 | B = VR<0.5 & EH 5-<6 | C = VR>=0.5 & EH 5-<6")
    print("No future outcome | no Formation | no sell rule | no threshold optimization")
    print("NOTE: A/B/C classification intentionally does NOT impose the old A2<09:30 gate; A2 clock is reported explicitly.")
    print("      This matches the current three-candidate question (VR x EH). Frozen V1 itself is NOT rewritten.")

    sources=[
        ("2026-09-15","stock_snapshot_2026-09-15(3).json"),
        ("2026-09-16","stock_snapshot_2026-09-16(3).json"),
        ("2026-09-17","stock_snapshot_2026-09-17(1).json"),
        ("2026-09-18","stock_snapshot_2026-09-18(1).json"),
    ]
    OUT=BASE/"_research_output"/"strong_4day_frozen_early_abc_buy_audit_2026_v1"
    OUT.mkdir(parents=True,exist_ok=True)

    find_attacks,compute_c_values,fill_entry_prices=load_engine()
    print("A1 PASS | original backend.events.attack_engine imported")

    all_rows=[]
    path_rows=[]
    total_roster=0

    for date,fn in sources:
        snap=choose_snapshot(date,fn)
        obj=json.loads(snap.read_text(encoding="utf-8-sig"))
        if str(obj.get("date"))!=date:
            stop(f"{date}: snapshot internal date={obj.get('date')}")
        roster=obj.get("passed",[]) or []
        if not roster:
            stop(f"{date}: passed roster empty")
        total_roster += len(roster)

        seen=set()
        day=[]
        for s in roster:
            sid=str(s.get("code") or s.get("stock_id") or "").zfill(4)
            name=str(s.get("name") or "")
            if sid in seen: stop(f"{date}: duplicate roster stock {sid}")
            seen.add(sid)

            d=bars_df(s.get("kbar_today"),date,sid)
            ctx=previous_context(s,date,sid)
            if d.empty or ctx is None:
                stop(f"{date}: DATA COVERAGE FAILED {sid} {name} | today/yesterday bars incomplete")
            prev_close,prev_vol=ctx

            # Proven historical routine: reconstruct key + original A1/A2 + A2 VR.
            a=reconstruct_a2(d,prev_close,prev_vol,find_attacks,compute_c_values,fill_entry_prices)
            base={
                "date":date,"stock_id":sid,"name":name,
                "strong_todayVol":s.get("todayVol",np.nan),
                "strong_volRatio":s.get("volRatio",np.nan),
                "strong_chgPct":s.get("chgPct",np.nan),
                "strong_price":s.get("price",np.nan),
                "prev_close":prev_close,
                **a
            }

            ac=a.get("attack_count",np.nan)
            a2=a.get("a2_end",np.nan)
            a2_up=bool(a.get("a2_upward",False))
            if pd.isna(ac) or float(ac)<2 or pd.isna(a2):
                day.append({**base,"status":"NO_BUY","signal_type":"NO_BUY",
                            "reason":"NO_ORIGINAL_A2"})
                continue
            if not a2_up:
                day.append({**base,"status":"NO_BUY","signal_type":"NO_BUY",
                            "reason":"A2_NOT_UPWARD"})
                continue

            # Frozen Early is replayed for every legal original upward A2.
            er=replay_early(d,a2)
            for pr in er.get("path_rows",[]):
                path_rows.append({"date":date,"stock_id":sid,"name":name,"a2_end":a2,**pr})

            if er["early_status"]!="EARLY":
                day.append({**base,
                    "early_status":er["early_status"],
                    "status":"NO_BUY","signal_type":"NO_BUY",
                    "reason":"FROZEN_EARLY_NOT_REACHED"})
                continue

            early_abs=float(er["early_abs"])
            entry_price,entry_time,entry_abs=next_minute_entry(d,early_abs)
            # EH is the frozen 09:00-09:10 key high relative to previous close,
            # same historical EarlyHigh coordinate used in the audited studies.
            eh=float(a["early_high_pct"])
            sig=candidate_type(float(a["a2_vr"]),eh)

            reason="" if sig!="NO_BUY" else "VR_EH_OUTSIDE_A_B_C"
            rec={**base,
                 "early_status":"EARLY",
                 "early_time":er.get("early_time",""),
                 "early_elapsed_min":er.get("early_elapsed_min",np.nan),
                 "early_price":er.get("early_price",np.nan),
                 "D_at_early_pct":er.get("early_D_from_A2_pct",np.nan),
                 "MFE_at_early_pct":er.get("early_MFE_from_A2_pct",np.nan),
                 "physical_state":er.get("physical_state",""),
                 "signal_type":sig,
                 "entry_time":entry_time,
                 "entry_price":entry_price,
                 "status":"BUY" if sig!="NO_BUY" else "NO_BUY",
                 "reason":reason}
            if sig!="NO_BUY" and not np.isfinite(entry_price):
                stop(f"{date} {sid}: BUY signal but no strict next-minute OPEN entry")
            day.append(rec)

        if len(day)!=len(roster) or len(seen)!=len(roster):
            stop(f"{date}: one-row-per-roster identity audit failed")
        all_rows.extend(day)

        dd=pd.DataFrame(day)
        print("\n"+date, "| snapshot:",snap.name)
        print(f"A2 PASS | roster={len(roster)} | coverage={len(day)}/{len(roster)}")
        print("SIGNALS:",dd.signal_type.value_counts(dropna=False).to_dict())

    full=pd.DataFrame(all_rows)
    if len(full)!=total_roster:
        stop(f"All-day identity mismatch {len(full)} != {total_roster}")
    if full.duplicated(["date","stock_id"]).any():
        stop("Duplicate date+stock_id in final roster")

    # Strong values are comparison-only and never used in recognition.
    for c in ["strong_todayVol","strong_volRatio","strong_chgPct","strong_price",
              "a2_vr","early_high_pct","early_elapsed_min","early_price",
              "D_at_early_pct","MFE_at_early_pct","entry_price"]:
        if c in full.columns:
            full[c]=pd.to_numeric(full[c],errors="coerce")

    buys=full[full.status=="BUY"].copy()
    counts=(full.groupby(["date","signal_type"]).size().unstack(fill_value=0)
            .reset_index())
    sig_summary=(buys.groupby("signal_type",as_index=False)
                 .agg(N=("stock_id","size"),
                      a2_vr_median=("a2_vr","median"),
                      earlyhigh_median=("early_high_pct","median"),
                      early_elapsed_median=("early_elapsed_min","median"),
                      D_at_early_median=("D_at_early_pct","median"),
                      MFE_at_early_median=("MFE_at_early_pct","median"),
                      strong_volRatio_median=("strong_volRatio","median"),
                      strong_chgPct_median=("strong_chgPct","median")))

    cols=["date","stock_id","name","signal_type",
          "strong_todayVol","strong_volRatio","strong_chgPct","strong_price",
          "key_price","a2_start","a2_end","a2_vr","early_high_pct",
          "early_time","early_elapsed_min","early_price",
          "D_at_early_pct","MFE_at_early_pct","physical_state",
          "entry_time","entry_price","status","reason"]
    cols=[c for c in cols if c in full.columns]
    full[cols].to_csv(OUT/"strong_all_roster_audit.csv",index=False,encoding="utf-8-sig")
    buys[cols].to_csv(OUT/"abc_buy_signals_only.csv",index=False,encoding="utf-8-sig")
    counts.to_csv(OUT/"signal_counts_by_day.csv",index=False,encoding="utf-8-sig")
    sig_summary.to_csv(OUT/"signal_numeric_summary.csv",index=False,encoding="utf-8-sig")
    if path_rows:
        pd.DataFrame(path_rows).to_csv(OUT/"frozen_early_causal_paths.csv",index=False,encoding="utf-8-sig")

    print("\n"+"="*200)
    print("BUY SIGNALS | STOCK-BY-STOCK + VALUES")
    print("="*200)
    if len(buys):
        show=["date","stock_id","name","signal_type","a2_end","a2_vr","early_high_pct",
              "early_time","early_elapsed_min","D_at_early_pct","MFE_at_early_pct",
              "entry_time","entry_price","strong_volRatio","strong_chgPct"]
        print(buys[show].sort_values(["date","signal_type","stock_id"])
              .to_string(index=False,float_format=lambda x:f"{x:.4f}"))
    else:
        print("(none)")

    print("\n"+"="*200)
    print("SIGNAL NUMERIC SUMMARY")
    print("="*200)
    print(sig_summary.to_string(index=False,float_format=lambda x:f"{x:.4f}") if len(sig_summary) else "(none)")

    print("\n"+"="*200)
    print("AUDIT PASSED | STRONG 4-DAY x A/B/C CAUSAL REPLAY COMPLETE")
    print("="*200)
    print(f"Roster total={total_roster} | BUY={len(buys)} | NO_BUY={len(full)-len(buys)}")
    print("Strong final values are comparison-only; they did NOT enter recognition.")
    print("Frozen V1 was NOT rewritten. A/B/C are current buy-candidate labels only.")
    print("Saved:",OUT)

if __name__=="__main__":
    main()