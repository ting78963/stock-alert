# -*- coding: utf-8 -*-
"""B v2 isolated namespace footprint audit; never constructs Runner or sends API/LINE.
Read-only; executes module top levels in a temporary clone only.
Estimated 20-120s; bottleneck: Attack/Early module top-level execution.
"""
import gc, os, runpy, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=["fugle_b_engine_v2_p1.py","run_strong_x_frozen_trend_live_auditor_v4.py","audit_strong_4day_frozen_early_abc_buy_2026_v1.py","f13_incremental_state.py"]
def rss():
    for s in Path("/proc/self/status").read_text().splitlines():
        if s.startswith("VmRSS:"):return int(s.split()[1])/1024
def main():
    print("B NAMESPACE MEMORY PROBE V2 | no Runner, network, LINE, or production writes",flush=True)
    missing=[p for p in FILES if not (ROOT/p).is_file()]
    if missing:sys.exit("STOP missing "+repr(missing))
    kept=[];gc.collect();base=rss();print(f"baseline={base:.2f} MiB",flush=True)
    checkpoints={0:base}
    start=time.monotonic()
    for i in range(1,51):
        bundle={}
        for name in FILES:
            # module namespaces are kept as each Runner does, but no load_attack_engine,
            # F13 binding, history loading, or per-stock state construction is performed.
            bundle[name]=runpy.run_path(str(ROOT/name),run_name="__b_probe_v2__")
        kept.append(bundle)
        if i in (1,5,10,20,30,40,50):
            gc.collect();m=rss();checkpoints[i]=m
            print(f"copies={i:2} RSS={m:.2f} MiB delta_from_baseline={m-base:.2f} MiB",flush=True)
    a=(checkpoints[50]-checkpoints[10])/40
    print(f"incremental RSS per namespace bundle copies 10..50={a:.3f} MiB",flush=True)
    print(f"elapsed={time.monotonic()-start:.1f}s",flush=True)
    print("LIMIT: excludes Runner rows, checkpoints, load_attack_engine, per-stock live state; NOT a 100-stock prediction.",flush=True)
if __name__=="__main__":main()
