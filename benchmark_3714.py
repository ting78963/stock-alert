from __future__ import annotations
from fugle_adapter import api_key,historical_1m,previous_context
from trend_engine import bars_df,reconstruct_a2,candidate_type,replay_early

EXPECTED={
 "stock_id":"3714","date":"2026-09-16","a2_end":"09:12:00",
 "a2_vr":0.22376843863067075,"early_high_pct":3.161397670549082,
 "signal_class":"A","frozen_early":"09:27:00",
 "early_d":1.453957996768973,"early_mfe":1.6155088852988664,
}
def _clock(x): return str(x)[-8:]
def run():
 key=api_key(); symbol=EXPECTED["stock_id"]; date=EXPECTED["date"]
 rows=historical_1m(symbol,date,key)
 pdate,pc,pv=previous_context(symbol,date,key)
 d=bars_df(rows,date,symbol)
 a2=reconstruct_a2(d,pc,pv)
 cls=candidate_type(float(a2["a2_vr"]),float(a2["early_high_pct"]))
 early=replay_early(d,a2["a2_end"])
 actual={
  "stock_id":symbol,"date":date,"prior_trading_date":pdate,
  "rows":len(d),"attack_count":int(a2["attack_count"]),
  "a2_end":_clock(a2["a2_end"]),"a2_vr":float(a2["a2_vr"]),
  "early_high_pct":float(a2["early_high_pct"]),"signal_class":cls,
  "frozen_early":_clock(early.get("early_time")),
  "early_d":float(early.get("early_D_from_A2_pct")),"early_mfe":float(early.get("early_MFE_from_A2_pct")),
 }
 checks={
  "a2_end":actual["a2_end"]==EXPECTED["a2_end"],
  "a2_vr":abs(actual["a2_vr"]-EXPECTED["a2_vr"])<1e-12,
  "early_high_pct":abs(actual["early_high_pct"]-EXPECTED["early_high_pct"])<1e-12,
  "signal_class":actual["signal_class"]==EXPECTED["signal_class"],
  "frozen_early":actual["frozen_early"]==EXPECTED["frozen_early"],
  "early_d":abs(actual["early_d"]-EXPECTED["early_d"])<1e-12,
  "early_mfe":abs(actual["early_mfe"]-EXPECTED["early_mfe"])<1e-12,
 }
 return {"audit":"PASS" if all(checks.values()) else "AUDIT FAILED -> STOP -> NO PRODUCTION SIGNAL",
         "line_sent":False,"writes_signal_state":False,"adds_watch_pool":False,
         "checks":checks,"actual":actual,"expected":EXPECTED}
