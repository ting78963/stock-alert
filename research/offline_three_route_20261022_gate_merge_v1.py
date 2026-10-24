#!/usr/bin/env python3
"""10/22 three-route minute-gate merge: COUNTERFACTUAL, not a handoff replay.
Inputs are the three independently observed read-only replay outputs.
A gate timestamp is NOT a delivery timestamp; FLOW FIFO and bridge receipt are unknown.
"""
from collections import Counter
DAY="2026-10-22"
# Measured first-pass minutes from the read-only Oct-22 runs.
VCP={"7711":"09:35"}
SURGE={"1809":"09:01","2406":"09:01","2468":"09:25","3406":"09:03","6179":"09:13","7711":"09:35","8240":"11:05"}
FLOW={"1809":"09:15","2406":"10:24","2468":"09:12","3406":"09:28","6179":"09:11","6277":"09:46","7711":"12:10","8240":"12:37","9933":"09:29"}
PRIORITY={"VCP":0,"SURGE":1,"FLOW":2}
assert len(set(VCP)|set(SURGE)|set(FLOW))==9
print("symbol,earliest_gate_minute,gate_route,tie_routes,flow_before_surge,actual_handoff")
counts=Counter()
for symbol in sorted(set(VCP)|set(SURGE)|set(FLOW)):
 events=[(minute,PRIORITY[route],route) for route,source in (("VCP",VCP),("SURGE",SURGE),("FLOW",FLOW)) if (minute:=source.get(symbol))]
 events.sort()
 minute,_,route=events[0]
 tied="/".join(e[2] for e in events if e[0]==minute)
 earlier=bool(symbol in FLOW and symbol in SURGE and FLOW[symbol]<SURGE[symbol])
 counts[route]+=1
 print(f"{symbol},{minute},{route},{tied},{earlier},UNVERIFIED")
assert counts=={"SURGE":4,"FLOW":4,"VCP":1},counts
assert VCP["7711"]==SURGE["7711"] and FLOW["2468"]<SURGE["2468"] and FLOW["6179"]<SURGE["6179"]
print("SUMMARY",dict(counts))
print("WARNING: Counterfactual first-gate winner only. Minute-bar proxies, blank VCP initial state, and F15-selected subset. Actual Scanner 5-second order, FIFO/ARM persistence, snapshot fields, bridge success, and same-day dedup are NOT replayed. Never treat these as actual alerts. No state writes or LINE.")
