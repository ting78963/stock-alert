# -*- coding: utf-8 -*-
"""Research-only fail-closed REST/canonical evidence comparison for B EOD.

Sparse minute bars are normal. 13:30 presence is NOT required.
This checks equality of returned REST bars and canonical rows, not exchange finality.
"""
from dataclasses import dataclass
FIELDS=("open","high","low","close","volume")
@dataclass(frozen=True)
class Comparison:
    ok:bool
    reason:str
    rest_count:int
    canonical_count:int

def compare_rest_canonical(rest,canonical,day,sid,tolerance=1e-7):
    sid=str(sid).zfill(4)
    def index(rows,source):
        d={}
        for row in rows:
            if str(row.get("date"))!=day or str(row.get("stock_id","")).zfill(4)!=sid:
                raise ValueError(source+"_identity")
            minute=str(row.get("minute",""))
            if not ("09:00:00"<=minute<="13:30:00"):
                raise ValueError(source+"_time")
            if minute in d:raise ValueError(source+"_duplicate")
            vals=tuple(float(row[k]) for k in FIELDS)
            if any(v!=v or abs(v)==float("inf") for v in vals):
                raise ValueError(source+"_nonfinite")
            d[minute]=vals
        return d
    try:
        r=index(rest,"rest");c=index(canonical,"canonical")
    except (ValueError,KeyError,TypeError) as exc:
        return Comparison(False,str(exc),len(rest),len(canonical))
    if not r:return Comparison(False,"empty_rest",0,len(c))
    if not c:return Comparison(False,"empty_canonical",len(r),0)
    if set(r)!=set(c):
        return Comparison(False,"minute_set_mismatch",len(r),len(c))
    for minute in sorted(r):
        if any(abs(a-b)>tolerance for a,b in zip(r[minute],c[minute])):
            return Comparison(False,"ohlcv_mismatch:"+minute,len(r),len(c))
    return Comparison(True,"bars_match_finality_unproven",len(r),len(c))
