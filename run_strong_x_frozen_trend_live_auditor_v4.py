from __future__ import annotations
r"""
STRONG JSON x EXACT FROZEN V1 x FINAL TREND FORMATION
Reusable Live Auditor v3 | 2026-09-16

永久版用途
==========
每天只要把：
    stock_snapshot_YYYY-MM-DD.json
直接丟到：
    C:/Users/<you>/Desktop/新增資料夾/
然後永遠執行本檔。

資料來源
========
- Strong 名單：JSON 的 passed（視為外部已觸發名單，不用收盤 chgPct 重篩）
- 今日 1 分 K：JSON kbar_today
- 前一交易日：JSON kbar_yesterday
    prev_close = 前一日最後一筆 close
    prev_day_volume = 前一日全部 minute volume 加總
- Strong VR5 平均量：
    avg5_volume = JSON todayVol / JSON volRatio
  只用來回推 Strong 首次觸發時間；不影響 Frozen V1。
- Attack：直接 import 原專案 backend.events.attack_engine.find_attacks
  絕不自行重寫 Attack。
- 不讀未來 D+1 outcome，不寫 DB，不修改任何原始檔。

Frozen V1（不調參）
===================
Key = 09:00:00~09:10:00（含）最高 high
Early High = Key / PrevClose - 1
A1/A2 = 原 attack_engine 從 09:10 起找出的第1/第2 Attack
A2 必須：
    3% <= Early High < 5%
    A2 end < 09:30
    Upward
    Attack VR = 累積量 through A2 end / 前一日全日量 < 0.5

Final Formation（已 frozen 的 exact reduced logic）
==================================================
A2 END 為 baseline。
從 A2 END 後切固定非重疊 5-min causal segments。
每一 segment endpoint 計算：
    Current D = current close / A2 close - 1
    MFE = running path high / A2 close - 1
逐 segment live replay：
    D Generation episode = positive raw delta-D 的 distinct episode
    Frontier episode = positive delta-MFE 的 distinct episode
只在合法 checkpoints +25/+50/+75/+100/+125 評估：
    D episodes >=2
    AND Frontier episodes >=2
    AND Current D >0
第一個成立 checkpoint = Formation / BUY。

Prev Close 永遠是 0% 座標；Formation 不重設整日價格座標。
"""

from pathlib import Path
from datetime import datetime, timedelta
import importlib
import json
import math
import sys
import numpy as np
import pandas as pd

HOME = Path.home()
BASE = HOME / "Desktop" / "新增資料夾"
PROJECT = HOME / "Desktop" / "taiwan-backtest-v9-final" / "taiwan-backtest-v9-final" / "tb-pkg"
OUTDIR = BASE / "_research_output" / "strong_x_frozen_trend_live_auditor"
CHECKPOINTS = [25, 50, 75, 100, 125]
SEGMENT_MINUTES = 5
EPS = 1e-12

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
        return int(h) * 60 + int(m) + float(sec) / 60.0
    except Exception:
        return np.nan

def episode_increment(prev_flag, flag):
    return int(bool(flag) and not bool(prev_flag))

def load_attack_engine():
    if not PROJECT.exists():
        raise FileNotFoundError(f"找不到原專案：{PROJECT}")
    sys.path.insert(0, str(PROJECT))
    ae = importlib.import_module("backend.events.attack_engine")
    find_attacks = getattr(ae, "find_attacks")
    compute_c_values = getattr(ae, "compute_c_values")
    fill_entry_prices = getattr(ae, "fill_entry_prices")
    return find_attacks, compute_c_values, fill_entry_prices

def load_snapshots():
    files = sorted(BASE.glob("stock_snapshot_*.json"))
    if not files:
        raise FileNotFoundError(f"{BASE} 找不到 stock_snapshot_*.json")
    records = []
    for fp in files:
        obj = json.loads(fp.read_text(encoding="utf-8-sig"))
        date = str(obj.get("date") or fp.stem.replace("stock_snapshot_", ""))
        for s in obj.get("passed", []) or []:
            records.append((date, fp.name, s))
    return files, records

def bars_df(items, fallback_date, sid):
    rows = []
    for b in items or []:
        rows.append({
            "date": str(b.get("date") or fallback_date),
            "stock_id": str(b.get("stock_id") or sid).zfill(4),
            "time": norm_time(b.get("minute") or b.get("time")),
            "open": b.get("open"),
            "high": b.get("high"),
            "low": b.get("low"),
            "close": b.get("close"),
            "volume": b.get("volume"),
        })
    d = pd.DataFrame(rows)
    if d.empty:
        return d
    for c in ["open","high","low","close","volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["time_str"] = d["time"].map(norm_time)
    d["minute_abs"] = d["time_str"].map(clock_minute)
    d = d.dropna(subset=["minute_abs","open","high","low","close","volume"])
    d = d.sort_values("minute_abs").reset_index(drop=True)
    return d

def previous_context(s, date, sid):
    y = bars_df(s.get("kbar_yesterday"), date, sid)
    if y.empty:
        return None, "no kbar_yesterday"
    prev_close = float(y.iloc[-1]["close"])
    prev_vol = float(y["volume"].clip(lower=0).sum())
    if not np.isfinite(prev_close) or prev_close <= 0:
        return None, "invalid prev_close"
    if not np.isfinite(prev_vol) or prev_vol <= 0:
        return None, "invalid prev_day_volume"
    return {
        "prev_date": str(y.iloc[-1]["date"]),
        "prev_close": prev_close,
        "prev_day_volume": prev_vol,
    }, ""

def first_true_time(z, mask):
    q = z[mask]
    return None if q.empty else str(q.iloc[0]["time_str"])

def strong_diagnostics(d, s, prev_close):
    """
    Diagnose each Strong gate independently, plus first simultaneous pass.
    Strong roster itself remains JSON passed; this is diagnostics only.

    Current Strong:
      change > 3%
      cumulative volume >= 4000 張
      cumulative amount >= NT$50m
      Strong VR5 >= 1.5

    avg5_volume is recovered from JSON final todayVol / final volRatio.
    """
    today_vol = pd.to_numeric(pd.Series([s.get("todayVol")]), errors="coerce").iloc[0]
    vr = pd.to_numeric(pd.Series([s.get("volRatio")]), errors="coerce").iloc[0]

    z = d.copy()
    z["cum_vol"] = z["volume"].clip(lower=0).cumsum()
    z["cum_amount"] = (z["close"] * z["volume"].clip(lower=0) * 1000.0).cumsum()
    z["change_pct_live"] = (z["close"] / prev_close - 1.0) * 100.0

    if np.isfinite(today_vol) and np.isfinite(vr) and vr > 0:
        avg5 = float(today_vol) / float(vr)
        z["strong_vr5_live"] = z["cum_vol"] / avg5
    else:
        avg5 = np.nan
        z["strong_vr5_live"] = np.nan

    m_chg = z["change_pct_live"] > 3.0
    m_vol = z["cum_vol"] >= 4000.0
    m_amt = z["cum_amount"] >= 50_000_000.0
    m_vr5 = z["strong_vr5_live"] >= 1.5
    m_all = m_chg & m_vol & m_amt & m_vr5

    def state_at(t):
        if not t:
            return {}
        q = z[z["time_str"] <= norm_time(t)]
        if q.empty:
            return {}
        r = q.iloc[-1]
        return {
            "change_pct": float(r["change_pct_live"]),
            "cum_vol": float(r["cum_vol"]),
            "cum_amount": float(r["cum_amount"]),
            "vr5": float(r["strong_vr5_live"]) if np.isfinite(r["strong_vr5_live"]) else np.nan,
        }

    return {
        "avg5_volume_recovered": avg5,
        "strong_time_chg_gt3": first_true_time(z, m_chg),
        "strong_time_vol_ge4000": first_true_time(z, m_vol),
        "strong_time_amt_ge50m": first_true_time(z, m_amt),
        "strong_time_vr5_ge1_5": first_true_time(z, m_vr5),
        "strong_first_time_rebuilt_gt3": first_true_time(z, m_all),
        "_strong_diag_frame": z,
    }

def reconstruct_v1(d, prev_close, prev_day_volume, find_attacks, compute_c_values, fill_entry_prices):
    # Exact frozen Key construction from prior validated replay.
    early = d[(d["time_str"] >= "09:00:00") & (d["time_str"] <= "09:10:00")]
    if early.empty:
        return {"v1_pass": False, "v1_reason": "no early bars"}

    key_price = float(early["high"].max())
    early_high_pct = (key_price / prev_close - 1.0) * 100.0

    # Original executable Attack engine, not a rewrite.
    attacks = find_attacks(d.copy(), key_price, "09:10:00", search_end="13:30:00")
    attacks = compute_c_values(attacks)
    attacks = fill_entry_prices(attacks, d)

    # cumulative volume through each actual minute
    dd = d.copy()
    dd["cum_vol"] = dd["volume"].clip(lower=0).cumsum()

    def cum_at(t):
        q = dd[dd["time_str"] <= norm_time(t)]
        return float(q.iloc[-1]["cum_vol"]) if not q.empty else np.nan

    rec = {
        "key_price": key_price,
        "early_high_pct": early_high_pct,
        "attack_count": len(attacks),
        "v1_pass": False,
        "v1_reason": "",
    }

    if len(attacks) < 2:
        rec["v1_reason"] = f"attack_count={len(attacks)} < 2"
        return rec

    a1, a2 = attacks[0], attacks[1]
    a1_end = norm_time(a1.get("end_time"))
    a2_start = norm_time(a2.get("start_time"))
    a2_end = norm_time(a2.get("end_time"))
    a2_vr = cum_at(a2_end) / prev_day_volume if prev_day_volume > 0 else np.nan
    is_up = bool(a2.get("is_upward"))
    attack_high = float(a2.get("attack_high") or np.nan)

    cond_early = 3.0 <= early_high_pct < 5.0
    cond_time = ("09:00:00" <= a2_end < "09:30:00")
    cond_up = is_up
    cond_vr = np.isfinite(a2_vr) and a2_vr < 0.5
    v1 = bool(cond_early and cond_time and cond_up and cond_vr)

    reasons = []
    if not cond_early: reasons.append("EarlyHigh_not_3_to_lt5")
    if not cond_time: reasons.append("A2_not_before_0930")
    if not cond_up: reasons.append("A2_not_upward")
    if not cond_vr: reasons.append("A2_VR_not_lt0.5")

    rec.update({
        "a1_end": a1_end,
        "a2_start": a2_start,
        "a2_end": a2_end,
        "a2_vr": a2_vr,
        "a2_upward": is_up,
        "a2_attack_high": attack_high,
        "v1_pass": v1,
        "v1_reason": "" if v1 else ";".join(reasons),
    })
    return rec

def displacement_state(d, a2_end_minute, checkpoint_abs_minute):
    # Exact frozen displacement semantics: baseline is last completed minute <= A2 end.
    a2rows = d[d["minute_abs"] <= a2_end_minute]
    if a2rows.empty:
        return None
    a2_close = float(a2rows.iloc[-1]["close"])

    path = d[
        (d["minute_abs"] > a2_end_minute) &
        (d["minute_abs"] <= checkpoint_abs_minute)
    ]
    if path.empty:
        current_close = a2_close
        max_high = a2_close
    else:
        current_close = float(path.iloc[-1]["close"])
        max_high = float(path["high"].max())

    current_d = (current_close / a2_close - 1.0) * 100.0
    mfe = (max_high / a2_close - 1.0) * 100.0
    return a2_close, current_close, current_d, mfe

def replay_formation(d, a2_end, prev_close):
    """
    Exact final Formation semantics:
    non-overlapping 5-minute trajectory anchored at A2 END;
    live episode counts over every segment;
    evaluate only +25/+50/+75/+100/+125.
    """
    start = clock_minute(a2_end)
    if not np.isfinite(start):
        return {"formation_status":"DATA_INCOMPLETE","formation_reason":"bad A2 end"}

    # Need enough day left to evaluate +125.
    max_obs = float(d["minute_abs"].max()) if len(d) else np.nan
    prev_d = 0.0
    prev_mfe = 0.0
    prev_pos_d = False
    prev_frontier = False
    d_eps = 0
    f_eps = 0
    event_rows = []
    cp_results = {}

    seg_end = start + SEGMENT_MINUTES
    while seg_end <= min(810.0, start + max(CHECKPOINTS)) + EPS:
        st = displacement_state(d, start, seg_end)
        if st is None:
            break
        a2_close, current_close, current_d, current_mfe = st

        pos_d = bool(np.isfinite(current_d) and np.isfinite(prev_d) and current_d - prev_d > 0)
        frontier = bool(np.isfinite(current_mfe) and np.isfinite(prev_mfe) and current_mfe > prev_mfe + EPS)
        d_eps += episode_increment(prev_pos_d, pos_d)
        f_eps += episode_increment(prev_frontier, frontier)

        minute = seg_end - start
        event_rows.append({
            "minutes_since_a2_end": minute,
            "current_close": current_close,
            "current_d": current_d,
            "current_mfe": current_mfe,
            "positive_d_event": pos_d,
            "d_episode_count": d_eps,
            "frontier_event": frontier,
            "frontier_episode_count": f_eps,
        })

        prev_d, prev_mfe = current_d, current_mfe
        prev_pos_d, prev_frontier = pos_d, frontier

        if int(round(minute)) in CHECKPOINTS:
            cp = int(round(minute))
            formed = (d_eps >= 2) and (f_eps >= 2) and (current_d > 0)
            cp_results[cp] = {
                "formed": formed, "current_close": current_close,
                "current_d": current_d, "current_mfe": current_mfe,
                "d_eps": d_eps, "f_eps": f_eps,
            }
            if formed:
                gain = (current_close / prev_close - 1.0) * 100.0
                return {
                    "formation_status":"FORMED",
                    "formation_checkpoint":cp,
                    "formation_time":norm_time(
                        (datetime(2000,1,1) + timedelta(minutes=seg_end)).time()
                    ),
                    "formation_gain_vs_prev_close_pct":gain,
                    "formation_d_episode_count":d_eps,
                    "formation_frontier_episode_count":f_eps,
                    "formation_current_d_pct":current_d,
                    "formation_mfe_from_a2_pct":current_mfe,
                    "formation_reason":"",
                }
        seg_end += SEGMENT_MINUTES

    if not np.isfinite(max_obs) or max_obs + EPS < start + max(CHECKPOINTS):
        return {
            "formation_status":"DATA_INCOMPLETE",
            "formation_checkpoint":np.nan,
            "formation_time":None,
            "formation_gain_vs_prev_close_pct":np.nan,
            "formation_d_episode_count":d_eps,
            "formation_frontier_episode_count":f_eps,
            "formation_reason":"day data ends before +125 checkpoint",
        }

    return {
        "formation_status":"NEVER_FORMED",
        "formation_checkpoint":np.nan,
        "formation_time":None,
        "formation_gain_vs_prev_close_pct":np.nan,
        "formation_d_episode_count":d_eps,
        "formation_frontier_episode_count":f_eps,
        "formation_reason":"",
    }

def main():
    print("="*190)
    print("STRONG JSON x EXACT FROZEN V1 x FINAL TREND FORMATION | REUSABLE AUDITOR v4")
    print("="*190)
    print("Original attack_engine | JSON today/yesterday bars | no DB write | no future outcome | no retune")
    print()

    find_attacks, compute_c_values, fill_entry_prices = load_attack_engine()
    files, records = load_snapshots()
    print("[SNAPSHOTS]", len(files), [x.name for x in files])
    print("[STRONG EXTERNAL ROSTER]", len(records))

    rows = []
    for date, source, s in records:
        sid = str(s.get("code") or s.get("stock_id") or "").zfill(4)
        name = s.get("name")
        d = bars_df(s.get("kbar_today"), date, sid)

        base = {
            "date": date, "stock_id": sid, "name": name, "source_json": source,
            "strong_json_todayVol": s.get("todayVol"),
            "strong_json_volRatio": s.get("volRatio"),
            "strong_json_chgPct": s.get("chgPct"),
            "strong_json_price": s.get("price"),
        }

        if d.empty:
            rows.append({**base, "status":"DATA_INCOMPLETE", "reason":"no kbar_today"})
            continue

        ctx, err = previous_context(s, date, sid)
        if ctx is None:
            rows.append({**base, "status":"DATA_INCOMPLETE", "reason":err})
            continue

        sd = strong_diagnostics(d, s, ctx["prev_close"])
        v1 = reconstruct_v1(
            d, ctx["prev_close"], ctx["prev_day_volume"],
            find_attacks, compute_c_values, fill_entry_prices
        )

        rec = {
            **base, **ctx,
            "strong_first_time_rebuilt_gt3": sd["strong_first_time_rebuilt_gt3"],
            "strong_time_chg_gt3": sd["strong_time_chg_gt3"],
            "strong_time_vol_ge4000": sd["strong_time_vol_ge4000"],
            "strong_time_amt_ge50m": sd["strong_time_amt_ge50m"],
            "strong_time_vr5_ge1_5": sd["strong_time_vr5_ge1_5"],
            "avg5_volume_recovered": sd["avg5_volume_recovered"],
            **v1,
        }

        # If Formation later exists, we fill its exact Strong-gate state below.
        rec["formation_strong_change_pct"] = np.nan
        rec["formation_strong_cum_vol"] = np.nan
        rec["formation_strong_cum_amount"] = np.nan
        rec["formation_strong_vr5"] = np.nan

        if v1.get("v1_pass"):
            form = replay_formation(d, v1.get("a2_end"), ctx["prev_close"])
            rec.update(form)
            if form.get("formation_status") == "FORMED" and form.get("formation_time"):
                zz = sd["_strong_diag_frame"]
                qq = zz[zz["time_str"] <= norm_time(form["formation_time"])]
                if not qq.empty:
                    rr = qq.iloc[-1]
                    rec["formation_strong_change_pct"] = float(rr["change_pct_live"])
                    rec["formation_strong_cum_vol"] = float(rr["cum_vol"])
                    rec["formation_strong_cum_amount"] = float(rr["cum_amount"])
                    rec["formation_strong_vr5"] = float(rr["strong_vr5_live"]) if np.isfinite(rr["strong_vr5_live"]) else np.nan
            rec["status"] = "OK"
            rec["reason"] = ""
        else:
            rec.update({
                "formation_status":"NOT_V1",
                "formation_checkpoint":np.nan,
                "formation_time":None,
                "formation_gain_vs_prev_close_pct":np.nan,
            })
            rec["status"] = "OK"
            rec["reason"] = v1.get("v1_reason","")

        # Whole D0 descriptors, descriptive only, not gates.
        rec["d0_close_return_vs_prev_pct"] = (float(d.iloc[-1]["close"]) / ctx["prev_close"] - 1.0) * 100.0
        rec["d0_full_mfe_vs_prev_pct"] = (float(d["high"].max()) / ctx["prev_close"] - 1.0) * 100.0
        rows.append(rec)

    out = pd.DataFrame(rows)
    OUTDIR.mkdir(parents=True, exist_ok=True)

    out_csv = OUTDIR / "strong_x_frozen_trend_latest_rows_v4.csv"
    sum_csv = OUTDIR / "strong_x_frozen_trend_latest_summary_v4.csv"
    man_json = OUTDIR / "strong_x_frozen_trend_latest_manifest_v3.json"
    out.to_csv(out_csv, index=False, encoding="utf-8-sig")

    summaries = []
    for date, g in out.groupby("date"):
        total = len(g)
        v1n = int(g.get("v1_pass", pd.Series(False,index=g.index)).fillna(False).astype(bool).sum())
        formed = int((g.get("formation_status", pd.Series("",index=g.index)) == "FORMED").sum())
        never = int((g.get("formation_status", pd.Series("",index=g.index)) == "NEVER_FORMED").sum())
        inc = int((g.get("status", pd.Series("",index=g.index)) == "DATA_INCOMPLETE").sum()) + int(
            (g.get("formation_status", pd.Series("",index=g.index)) == "DATA_INCOMPLETE").sum()
        )
        summaries.append({
            "date":date, "strong_n":total, "v1_n":v1n, "formation_n":formed,
            "never_formed_n":never, "data_incomplete_n":inc,
            "v1_pct_of_strong":100*v1n/total if total else np.nan,
            "formation_pct_of_strong":100*formed/total if total else np.nan,
            "formation_pct_of_v1":100*formed/v1n if v1n else np.nan,
        })
    summary = pd.DataFrame(summaries)
    summary.to_csv(sum_csv, index=False, encoding="utf-8-sig")

    print("\n"+"="*190)
    print("DAILY SUMMARY")
    print("="*190)
    print(summary.to_string(index=False, float_format=lambda x:f"{x:.2f}"))

    print("\n"+"="*190)
    print("STOCK-BY-STOCK")
    print("="*190)
    show = [
        "date","stock_id","name","strong_json_chgPct","strong_json_volRatio",
        "strong_time_chg_gt3","strong_time_vol_ge4000","strong_time_amt_ge50m",
        "strong_time_vr5_ge1_5","strong_first_time_rebuilt_gt3",
        "early_high_pct","attack_count","a2_end","a2_vr","v1_pass","v1_reason",
        "formation_status","formation_checkpoint","formation_time",
        "formation_gain_vs_prev_close_pct",
        "formation_strong_change_pct","formation_strong_cum_vol",
        "formation_strong_cum_amount","formation_strong_vr5",
        "d0_close_return_vs_prev_pct","d0_full_mfe_vs_prev_pct"
    ]
    show = [c for c in show if c in out.columns]
    print(out[show].sort_values(["date","stock_id"]).to_string(
        index=False, float_format=lambda x:f"{x:.4f}"
    ))


    print("\n"+"="*190)
    print("FROZEN V1 FAILURE ANATOMY | Strong roster only")
    print("="*190)
    nonv1 = out[~out.get("v1_pass", pd.Series(False,index=out.index)).fillna(False).astype(bool)].copy()
    reason_tokens = [
        ("EarlyHigh_not_3_to_lt5", "Early High 不在 3%~<5%"),
        ("attack_count=", "Attack 不足 2 次"),
        ("A2_not_before_0930", "A2 不在 09:30 前"),
        ("A2_not_upward", "A2 非 Upward"),
        ("A2_VR_not_lt0.5", "A2 VR >= 0.5"),
    ]
    for token, label in reason_tokens:
        n = int(nonv1["v1_reason"].fillna("").str.contains(token, regex=False).sum())
        print(f"{label:<28} {n:>3} / {len(nonv1)}")
    print("注意：原因可重疊，所以加總可大於 NOT_V1 檔數。")

    # Natural anatomy of Early High failures: below 3 vs >=5 (no threshold scan; frozen boundaries only)
    if "early_high_pct" in nonv1:
        eh = pd.to_numeric(nonv1["early_high_pct"], errors="coerce")
        print(f"  ├─ Early High <3%             {int((eh < 3).sum()):>3}")
        print(f"  └─ Early High >=5%            {int((eh >= 5).sum()):>3}")

    fail_csv = OUTDIR / "strong_x_frozen_v1_failure_anatomy_v4.csv"
    fail_cols = [c for c in [
        "date","stock_id","name","early_high_pct","attack_count","a2_end","a2_vr",
        "v1_reason","d0_close_return_vs_prev_pct","d0_full_mfe_vs_prev_pct"
    ] if c in nonv1.columns]
    nonv1[fail_cols].to_csv(fail_csv,index=False,encoding="utf-8-sig")

    manifest = {
        "version":"v4",
        "snapshots":[x.name for x in files],
        "strong_external_roster_n":len(records),
        "attack_engine":str(PROJECT / "backend" / "events" / "attack_engine.py"),
        "frozen_v1":{
            "key":"09:00 through 09:10 inclusive high",
            "A2":"original attack_engine second attack after 09:10",
            "early_high":"3 <= pct < 5",
            "a2_end":"<09:30",
            "upward":True,
            "attack_vr":"cum volume through A2 end / previous day full-day volume <0.5"
        },
        "formation":{
            "baseline":"A2 end close",
            "segment_minutes":5,
            "checkpoints":CHECKPOINTS,
            "d_generation":">=2 distinct positive raw-delta-D episodes",
            "frontier":">=2 distinct positive MFE-extension episodes",
            "current_d":">0",
            "buy":"first legal checkpoint satisfying all"
        },
        "future_outcome_opened":False,
        "threshold_scan":False,
        "retune":False,
        "vcp_used":False,
        "outputs":[str(out_csv),str(sum_csv)]
    }
    man_json.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")

    print("\nOUTPUT:")
    print(out_csv)
    print(sum_csv)
    print(man_json)
    print("\nDONE.")

if __name__ == "__main__":
    main()
