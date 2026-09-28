# -*- coding: utf-8 -*-
"""Official TWSE session gate. Fail closed on unavailable/ambiguous schedule data."""
from __future__ import annotations
import json, os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

TPE=ZoneInfo("Asia/Taipei")
URL="https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"

class SessionGateError(RuntimeError): pass

def _ymd(x):
    s=str(x or "").strip().replace("/","-")
    # Official API commonly exposes Gregorian date; tolerate ROC yyyMMdd-ish forms too.
    for fmt in ("%Y-%m-%d","%Y%m%d"):
        try: return datetime.strptime(s,fmt).date()
        except ValueError: pass
    if len(s)>=7 and s[:3].isdigit():
        digits="".join(ch for ch in s if ch.isdigit())
        if len(digits)==7:
            return date(int(digits[:3])+1911,int(digits[3:5]),int(digits[5:7]))
    return None

def fetch_schedule(timeout=10):
    r=requests.get(URL,timeout=timeout,headers={"Accept":"application/json"})
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,list) or not data:
        raise SessionGateError("TWSE holiday schedule empty/invalid")
    return data

def is_scheduled_open(day=None, rows=None):
    day=day or datetime.now(TPE).date()
    if day.weekday()>=5: return False
    rows=rows if rows is not None else fetch_schedule()
    same=[]
    for row in rows:
        vals=list(row.values()) if isinstance(row,dict) else []
        dates=[_ymd(v) for v in vals]
        if day in dates: same.append(row)
    if not same:
        # Weekday absent from official exception/holiday table => scheduled trading day.
        return True
    text=" ".join(str(v) for row in same for v in row.values())
    # Explicit "start/resume trading" entries are open; all other dated exceptions fail closed.
    open_words=("開始交易","恢復交易","start trading","resume trading")
    return any(w.lower() in text.lower() for w in open_words)

def assert_open_today():
    d=datetime.now(TPE).date()
    if not is_scheduled_open(d):
        raise SessionGateError(f"TWSE scheduled closed: {d.isoformat()}")
    return d.isoformat()

if __name__=="__main__":
    print(assert_open_today())
