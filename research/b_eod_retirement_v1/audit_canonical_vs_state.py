# -*- coding: utf-8 -*-
"""READ ONLY: compare persisted B canonical minutes with runner state and events.
Does not establish Fugle REST final authority or retire workers.
"""
import argparse,json
from pathlib import Path
def audit(root,day):
    base=Path(root)/"b_live_runner_v2_p1"/day
    if not base.is_dir():raise SystemExit("[STOP] missing B day folder")
    print("stock_id,state_through,canonical_last,canonical_count,state_count,rest_reconciles,event_count,unsent_event,issues")
    n=0; bad=0; noevent=0
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        sid=folder.name.zfill(4); issues=[]
        try:
            state=json.loads((folder/"runner_state.json").read_text(encoding="utf-8"))
            raw=(folder/"canonical_minutes.jsonl").read_text(encoding="utf-8").splitlines()
            rows=[json.loads(x) for x in raw if x.strip()]
        except Exception as exc:
            print(sid+",,,,,,,,read_error_"+type(exc).__name__);bad+=1;n+=1;continue
        keys=[str(x.get("minute","")) for x in rows]
        if not rows:issues.append("empty_canonical")
        if keys!=sorted(set(keys)):issues.append("unordered_or_duplicate")
        if any(str(x.get("date"))!=day or str(x.get("stock_id","")).zfill(4)!=sid for x in rows):
            issues.append("canonical_identity")
        if state.get("date")!=day or str(state.get("stock_id","")).zfill(4)!=sid:
            issues.append("state_identity")
        last=max(keys) if keys else ""
        through=str(state.get("through",""))
        if last!=through:issues.append("state_canonical_last_mismatch")
        if state.get("canonical_minutes")!=len(rows):issues.append("count_mismatch")
        events=[]
        for name in ("signal_event.json","p1_signal_event.json"):
            p=folder/name
            if p.exists():
                try:
                    e=json.loads(p.read_text(encoding="utf-8"));events.append(e)
                    if e.get("date")!=day or str(e.get("stock_id","")).zfill(4)!=sid:issues.append("event_identity")
                except Exception:issues.append("event_read_error")
        unsent=any(e.get("line_sent") is not True for e in events)
        if unsent:issues.append("unsent_event")
        if not events:noevent+=1
        n+=1;bad+=bool(issues)
        print(",".join(map(str,[sid,through,last,len(rows),state.get("canonical_minutes"),state.get("rest_reconciles"),len(events),int(unsent),"|".join(issues)])))
    print("SUMMARY",{"folders":n,"no_event":noevent,"issue_folders":bad})
    print("LIMIT: REST finality, LINE side effects and live thread exit NOT verified.")
    return 2 if bad or not n else 0
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",default="/var/data/stock-alert");p.add_argument("--date",required=True)
    a=p.parse_args();raise SystemExit(audit(a.root,a.date))
