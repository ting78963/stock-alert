from __future__ import annotations
import json,os,threading,time
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from abc_buy_flex import abc_buy_flex
from fugle_adapter import api_key,intraday_1m,previous_context,DataError
from trend_engine import bars_df,reconstruct_a2,candidate_type,replay_early

TPE=ZoneInfo("Asia/Taipei")
STATE_DIR=Path(os.environ.get("ABC_STATE_DIR","/tmp/stock-alert-abc"))
STATE_DIR.mkdir(parents=True,exist_ok=True)
_lock=threading.Lock()
_watch={}
_sent=set()
_state_date=None

def _clock(s): return str(s)[:8]
def _today(): return datetime.now(TPE).date().isoformat()

def _reset_day():
    global _state_date
    d=_today()
    with _lock:
        if d!=_state_date:
            _state_date=d; _watch.clear(); _sent.clear()

def _post_flex(msg,line_token,group_id):
    import requests
    if not line_token or not group_id:
        print(json.dumps(msg,ensure_ascii=False),flush=True); return False
    r=requests.post("https://api.line.me/v2/bot/message/push",
      headers={"Authorization":f"Bearer {line_token}","Content-Type":"application/json"},
      json={"to":group_id,"messages":[msg]},timeout=10)
    print(f"LINE ABC: {r.status_code}",flush=True)
    return 200<=r.status_code<300

def discover(symbol,discovered_at=None,name=None):
    """A hands a stock to B once. B owns all later trend tracking."""
    _reset_day(); symbol=str(symbol).zfill(4)
    discovered_at=discovered_at or datetime.now(TPE).strftime("%H:%M:%S")
    with _lock:
        if symbol in _watch:return False
        _watch[symbol]={"discovered_at":_clock(discovered_at),"name":name}
    print(f"B DISCOVER {symbol} at {discovered_at}",flush=True)
    return True

def _completed_cutoff():
    # A bar labelled HH:MM is eligible only after that minute has completed.
    n=datetime.now(TPE)
    return (n-timedelta(minutes=1)).strftime("%H:%M:59")

def _evaluate(symbol,meta,line_token,group_id):
    date=_today(); cutoff=_completed_cutoff()
    key=api_key(); rows=intraday_1m(symbol,date,key)
    rows=[r for r in rows if _clock(r["minute"])<=cutoff]
    if not rows:
        print(f"B EVAL {symbol} result=WAIT reason=NO_MINUTE_ROWS cutoff={cutoff}",flush=True)
        return

    # Production semantics: discovery is the A->B handoff boundary, not a
    # permanent data cutoff. Every evaluation uses only bars completed NOW.
    # This naturally replays 09:00->discovery and then continues causally with
    # each newly completed minute after discovery. No future bar is available.
    discovered=_clock(meta["discovered_at"])
    if not any(_clock(r["minute"])<=discovered for r in rows):
        print(f"B EVAL {symbol} result=WAIT reason=NO_ROWS_BY_DISCOVERY discovery={discovered}",flush=True)
        return
    pdate,pc,pv=previous_context(symbol,date,key)
    d=bars_df(rows,date,symbol)
    if d.empty:raise DataError("empty canonical minute store")
    a2=reconstruct_a2(d,pc,pv)
    attacks=a2.get("attack_count",0)
    upward=bool(a2.get("a2_upward"))
    if attacks<2 or not upward:
        print(f"B EVAL {symbol} bars={len(d)} attacks={attacks} a2_upward={upward} result=WAIT reason=NO_VALID_A2",flush=True)
        return
    vr=float(a2.get("a2_vr"))
    eh=float(a2.get("early_high_pct"))
    cls=candidate_type(vr,eh)
    if cls=="NO_BUY":
        print(f"B EVAL {symbol} bars={len(d)} a2={_clock(a2.get('a2_end'))} vr={vr:.6f} eh={eh:.6f} candidate=NO_BUY result=NO_BUY",flush=True)
        return
    early=replay_early(d,a2.get("a2_end"))
    early_status=early.get("early_status")
    if early_status!="EARLY":
        print(f"B EVAL {symbol} bars={len(d)} a2={_clock(a2.get('a2_end'))} vr={vr:.6f} eh={eh:.6f} candidate={cls} early={early_status} result=WAIT",flush=True)
        return
    print(f"B EVAL {symbol} bars={len(d)} a2={_clock(a2.get('a2_end'))} vr={vr:.6f} eh={eh:.6f} candidate={cls} early=EARLY early_time={_clock(early.get('early_time'))}",flush=True)

    recognition=_clock(early["early_time"])
    live_known=max(recognition,discovered)
    event_id=f"{date}:{symbol}:{cls}:{recognition}:{live_known}"
    with _lock:
        if event_id in _sent:return

    event={
      "schema":"abc_signal_v1","date":date,"stock_id":symbol,"signal_class":cls,
      "discovered_at":discovered,"recognition_time":recognition,"live_known_time":live_known,
      "a2_end":_clock(a2.get("a2_end")),"a2_vr":float(a2.get("a2_vr")),
      "early_high_pct":float(a2.get("early_high_pct")),"frozen_early_price":float(early.get("early_price")),
      "late_discovery":recognition<discovered,"source":"Fugle","line_sent":False,
      "prior_trading_date":pdate
    }
    ok=_post_flex(abc_buy_flex(event,meta.get("name")),line_token,group_id)
    if not ok:return
    event["line_sent"]=True
    with _lock:_sent.add(event_id)
    p=STATE_DIR/f"{date}_{symbol}_{cls}.json"
    p.write_text(json.dumps(event,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"ABC SIGNAL {symbol} {cls} recognition={recognition} live_known={live_known}",flush=True)

def attack_trace(symbol,meta):
    """Read-only causal trace through discovery, aligned with live-partial Attack semantics."""
    date=_today(); key=api_key(); discovered=_clock(meta["discovered_at"])
    rows=intraday_1m(symbol,date,key)
    replay_rows=[r for r in rows if _clock(r["minute"])<=discovered]
    pdate,pc,pv=previous_context(symbol,date,key)
    d=bars_df(replay_rows,date,symbol)
    if d.empty: raise DataError("empty canonical minute store")
    early=d[(d.time_str>="09:00:00")&(d.time_str<="09:10:00")]
    if early.empty: raise DataError("no 09:00-09:10 bars")
    key_price=float(early.high.max())
    source=str(early.loc[early.high==key_price].iloc[0].time_str)
    search=d[(d.time_str>"09:10:00")&(d.time_str<=discovered)].reset_index(drop=True)
    before=d[d.time_str<="09:10:00"]
    prev_close=float(before.iloc[-1].close) if len(before) else key_price
    in_attack=False; attack_no=0; trace=[]
    for _,row in search.iterrows():
        t=str(row.time_str); h=float(row.high); close=float(row.close)
        trigger=(not in_attack and prev_close<key_price and h>=key_price)
        event=""
        if trigger:
            in_attack=True; attack_no+=1; event=f"A{attack_no}_START"
        # IMPORTANT: discovery is a partial live cutoff. Do NOT close an open
        # Attack merely because this is the last replay row. This matches
        # production find_attacks(..., finalize_last=False) before 13:30.
        if in_attack and close<key_price:
            event=(event+"+" if event else "")+f"A{attack_no}_END"
            in_attack=False
        trace.append({"minute":t,"prev_close":prev_close,"high":h,"close":close,
                      "key":key_price,"trigger":trigger,"event":event,
                      "in_attack_after_bar":in_attack})
        prev_close=close
    a2=reconstruct_a2(d,pc,pv)
    return {"audit":"TRACE_ONLY_NO_SIGNAL_MUTATION","stock_id":symbol,"date":date,
            "discovered_at":discovered,"bars":len(d),"key_price":key_price,
            "key_source_time":source,"key_confirmed_time":"09:10:00",
            "attack_count":a2.get("attack_count",0),"open_attack_state":bool(in_attack),
            "open_attack_no":attack_no if in_attack else None,
            "a2":a2,"trace":trace}

def monitor_loop(line_token,group_id,interval=15):
    """REST-reconciled B runner. No synthetic minutes; no backdating; one event per id."""
    while True:
        try:
            _reset_day()
            n=datetime.now(TPE); m=n.hour*60+n.minute
            if n.weekday()<5 and 540<=m<=810:
                with _lock: items=list(_watch.items())
                for symbol,meta in items:
                    try:_evaluate(symbol,meta,line_token,group_id)
                    except Exception as e:print(f"B {symbol} error: {e}",flush=True)
        except Exception as e:print(f"B monitor error: {e}",flush=True)
        time.sleep(interval)

def status():
    _reset_day()
    with _lock:return {"watching":len(_watch),"symbols":list(_watch),"sent":len(_sent)}
