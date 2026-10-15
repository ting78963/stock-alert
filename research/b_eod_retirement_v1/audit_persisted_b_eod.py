# -*- coding: utf-8 -*-
"""Read-only audit of persisted B state at EOD. No imports of production modules.
Does not assert that a 13:30 bar must exist for every symbol (no-trade minutes).
"""
import argparse, collections, json
from pathlib import Path

def run(root,day):
    base=Path(root)/"b_live_runner_v2_p1"/day
    if not base.is_dir():
        print("[STOP] B day directory missing:",base);return 2
    totals=collections.Counter()
    print("date,stock_id,through,canonical_minutes,rest_reconciles,abc_event,p1_event,line_sent,issue")
    for folder in sorted(base.iterdir()):
        if not folder.is_dir():continue
        sid=folder.name.zfill(4)
        state=folder/"runner_state.json"
        issues=[]; st={}
        if not state.is_file():issues.append("missing_state")
        else:
            try:st=json.loads(state.read_text(encoding="utf-8"))
            except Exception:issues.append("unreadable_state")
        if st:
            if st.get("date")!=day or str(st.get("stock_id","")).zfill(4)!=sid:issues.append("identity_mismatch")
        events=[]
        for name in ("signal_event.json","p1_signal_event.json"):
            p=folder/name
            if p.is_file():
                try:
                    e=json.loads(p.read_text(encoding="utf-8"))
                    if e.get("date")!=day or str(e.get("stock_id","")).zfill(4)!=sid:issues.append("event_identity_mismatch")
                    events.append(e)
                except Exception:issues.append("unreadable_event")
        sent=any(e.get("line_sent") is True for e in events)
        if events and not sent:issues.append("event_without_confirmed_line")
        if not events:totals["no_event"]+=1
        if sent:totals["line_confirmed"]+=1
        if issues:totals["issue"]+=1
        totals["folders"]+=1
        print(",".join(map(str,[day,sid,st.get("through",""),st.get("canonical_minutes",""),st.get("rest_reconciles",""),int((folder/"signal_event.json").exists()),int((folder/"p1_signal_event.json").exists()),int(sent),"|".join(issues)])))
    print("SUMMARY",dict(totals))
    print("IMPORTANT: state.through is not authoritative REST finality; this audit makes no retirement decisions.")
    return 2 if totals["issue"] or not totals["folders"] else 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="/var/data/stock-alert")
    p.add_argument("--date",required=True)
    a=p.parse_args()
    raise SystemExit(run(a.root,a.date))
