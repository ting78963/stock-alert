#!/usr/bin/env python3
"""Offline A ticker cache-miss blocking proof. Extract actual method, fake HTTP."""
import ast,types,urllib.parse,json
from pathlib import Path
s=Path("/tmp/a_ticker_stage.py").read_text(encoding="utf-8")
t=ast.parse(s)
adapter=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=="FugleAdapter")
ticker=next(n for n in adapter.body if isinstance(n,ast.FunctionDef) and n.name=="ticker")
ns={"Dict":dict,"Any":object,"urllib":types.SimpleNamespace(parse=urllib.parse),
    "BASE":"https://fake.invalid","AuditStop":RuntimeError,"json":json}
requests=[]
def fake_http(url,key):
    requests.append(url)
    return {"symbol":url.rsplit("/",1)[-1],"market":"TSE","securityType":"01","industry":"24"}
ns["http_json"]=fake_http
class FakePath:
    suffix = '.json'
    def mkdir(self,**kw):pass
    def with_suffix(self,s):return self
    def write_text(self,*a,**kw):pass
    def replace(self,*a):pass
    @property
    def parent(self):return self
ns["F11_METADATA_CACHE_FILE"]=FakePath()
exec(compile(ast.fix_missing_locations(ast.Module(body=[ticker],type_ignores=[])),"<ticker>","exec"),ns)
obj=types.SimpleNamespace(key="FAKE",meta_cache={},f11_metadata_cache={},f11_metadata_store={})
ns["ticker"](obj,"1111")
assert len(requests)==1
ns["ticker"](obj,"1111")
assert len(requests)==1
obj.f11_metadata_cache["2222"]={"symbol":"2222","market":"TSE","securityType":"01","industry":"24"}
ns["ticker"](obj,"2222")
assert len(requests)==1
print("PASS: F11 cache MISS causes direct synchronous HTTP inside ticker")
print("PASS: same-symbol RAM cache prevents second request")
print("PASS: persisted F11 hit avoids HTTP")
print("RISK: first MISS is blocking; latency not measured with real API")
print("HTTP=MOCKED; REAL A/B/LINE=NONE; PRODUCTION_WRITES=NONE")
