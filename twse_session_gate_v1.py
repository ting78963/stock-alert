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

# Extraordinary market-wide closure absent from the annual TWSE holiday calendar.
EXTRAORDINARY_CLOSED_DAYS = frozenset({date(2026, 10, 23)})

# Frozen from TWSE's published 115 (2026) annual trading calendar.
# The live OpenAPI endpoint can switch to the next year's schedule early.
TWSE_2026_CLOSED = frozenset(date.fromisoformat(x) for x in (
    "2026-01-01", "2026-02-12", "2026-02-13", "2026-02-16",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-27", "2026-04-03", "2026-04-06", "2026-05-01",
    "2026-06-19", "2026-09-25", "2026-09-28", "2026-10-09",
    "2026-10-26", "2026-12-25",
))

def _ymd(x):
    s=str(x or "").strip().replace("/","-")
    digits=''.join(ch for ch in s if ch.isdigit())
    # Parse seven-digit ROC dates first: %Y%m%d misreads 1151026 as year 1151.
    if len(digits)==7 and s.replace('-','').isdigit():
        try: return date(int(digits[:3])+1911,int(digits[3:5]),int(digits[5:7]))
        except ValueError: return None
    for fmt in ('%Y-%m-%d','%Y%m%d'):
        try: return datetime.strptime(s,fmt).date()
        except ValueError: pass
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
    if day.weekday()>=5 or day in EXTRAORDINARY_CLOSED_DAYS: return False
    rows=rows if rows is not None else fetch_schedule()
    # TWSE official schema uses Date=ROC yyyMMdd (e.g. 1150928).
    # Match the Date field explicitly; never infer a date by scanning arbitrary values.
    same=[]
    parsed_dates=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        d=_ymd(row.get("Date"))
        if d is not None:
            parsed_dates.append(d)
            if d==day: same.append(row)
    if not parsed_dates:
        raise SessionGateError("TWSE holiday schedule has no parseable Date rows")
    # Fail closed if the returned annual schedule is for a different year.
    if day.year not in {d.year for d in parsed_dates}:
        if day.year == 2026:
            return day not in TWSE_2026_CLOSED
        raise SessionGateError(f"TWSE holiday schedule does not cover {day.year}")
    if not same:
        return True
    text=" ".join(str(v) for row in same for v in row.values())
    open_words=("開始交易","恢復交易","start trading","resume trading")
    return any(w.lower() in text.lower() for w in open_words)

def assert_open_today():
    d=datetime.now(TPE).date()
    if not is_scheduled_open(d):
        raise SessionGateError(f"TWSE scheduled closed: {d.isoformat()}")
    return d.isoformat()

if __name__=="__main__":
    print(assert_open_today())
