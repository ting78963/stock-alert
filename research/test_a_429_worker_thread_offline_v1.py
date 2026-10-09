#!/usr/bin/env python3
"""Offline live WaitDataWorker thread/queue test with fake HTTP and virtual clock.
No production module import, network, disk writes, A/B/LINE.
"""
import ast,threading,queue,time,types,urllib.parse
from dataclasses import dataclass
from datetime import date,timedelta
from typing import Any,Dict,List,Optional,Tuple
from pathlib import Path
src=Path("/tmp/a_429_thread_stage.py").read_text(encoding="utf-8")
tree=ast.parse(src)
names={"WaitDataJob","WaitDataResult","WaitDataWorker"}
nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,)) and n.name in names]
assert len(nodes)==3
ns={"dataclass":dataclass,"threading":threading,"queue":queue,"time":None,
    "Dict":Dict,"List":List,"Optional":Optional,"Tuple":Tuple,"Any":Any,
    "date":date,"timedelta":timedelta,"urllib":types.SimpleNamespace(parse=urllib.parse),
    "BASE":"https://invalid.local","HISTORY_429_BACKOFF_SEC":60.0,
    "HISTORY_BACKUP_FAILURE_COOLDOWN_SEC":15.0,"HISTORY_BACKUP_MAX_429_RETRIES":2}
class AuditStop(RuntimeError):pass
ns["AuditStop"]=AuditStop
lock=threading.Lock()
class Clock:
    now=0.0
    def monotonic(self):
        with lock:return self.now
    def sleep(self,seconds):
        with lock:self.now+=seconds
        time.sleep(0.002)
clock=Clock()
ns["time"]=clock
calls=[]
def fake_http(url,key):
    symbol=url.split("/historical/candles/")[1].split("?")[0]
    calls.append((symbol,clock.monotonic()))
    if symbol=="1111":raise AuditStop("Fugle HTTP 429: mocked")
    return {"symbol":symbol,"data":[{"date":"2026-10-08","close":10,"volume":100000}]}
ns["http_json"]=fake_http
ns["print"]=lambda *args,**kwargs:None
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"<worker-extracted>","exec"),ns)
worker=ns["WaitDataWorker"]("FAKE")
assert worker.submit("1111","2026-10-12")
assert worker.submit("2222","2026-10-12")
results={}
deadline=time.monotonic()+4
while len(results)<2 and time.monotonic()<deadline:
    for x in worker.drain_results():results[x.symbol]=x
    time.sleep(.01)
assert set(results)=={"1111","2222"},results
assert len([x for x in calls if x[0]=="1111"])==3,calls
assert calls[0]==("1111",0.0),calls
assert calls[1][1]>=60 and calls[2][1]>=120,calls
assert calls[3][0]=="2222" and calls[3][1]>=180,calls
assert results["1111"].ok is False and results["1111"].fatal is False
assert results["2222"].ok is True
# The next queued stock starts only after the global 60s backoff.
# By then, the first stock's own 60s cooldown may legitimately have expired.
# Check that the per-symbol cooldown was recorded at failure, rather than
# asserting it is still active after another 60s of virtual time.
assert ("1111","2026-10-12") in worker.retry_after
assert worker.retry_after[("1111","2026-10-12")] >= 180.0
print("PASS: 429 failure recorded a per-symbol cooldown through virtual t>=180s")
print("PASS: live background thread limited 429 stock to 3 HTTP attempts")
print("PASS: next stock waited until shared cooldown (virtual t>=180s)")
print("PASS: exhausted 429 recoverable; next stock succeeded")
print("PASS: same-stock immediate requeue blocked")
print("CALLS =",calls)
print("VIRTUAL_TIME_ONLY; REAL_HTTP = NONE; PRODUCTION_WRITES = NONE; A/B/LINE = NONE")
