# -*- coding: utf-8 -*-
"""One-shot smoke test for the read-only Fugle web proxy adapter.
No production state writes. No LINE. No A/B logic changes.
"""
from __future__ import annotations
import json
from fugle_web_proxy import bp
from flask import Flask

app=Flask(__name__)
app.register_blueprint(bp)

def main():
    with app.test_client() as c:
        s=c.get("/public/fugle/snapshot")
        print("SNAPSHOT_HTTP",s.status_code)
        sj=s.get_json(silent=True) or {}
        rows=sj.get("data") or []
        print("SNAPSHOT_OK",sj.get("ok"),"ROWS",len(rows),"DATE",sj.get("date"))
        if s.status_code!=200 or not sj.get("ok") or not rows:
            raise SystemExit("FAIL snapshot")
        sample=next((x for x in rows if x.get("stock_id")=="2330"),rows[0])
        sid=str(sample["stock_id"])
        print("SAMPLE",sid, sample.get("stock_name"),
              "chg",sample.get("change_rate"),"amount",sample.get("total_amount"),
              "volume_lots",sample.get("total_volume"))
        d=c.get(f"/public/fugle/daily/{sid}?from=2026-09-01&to=2026-09-28")
        print("DAILY_HTTP",d.status_code)
        dj=d.get_json(silent=True) or {}
        dr=dj.get("data") or []
        print("DAILY_OK",dj.get("ok"),"ROWS",len(dr))
        if d.status_code!=200 or not dj.get("ok") or not dr:
            raise SystemExit("FAIL daily")
        required={"date","open","max","min","close","Trading_Volume"}
        missing=required-set(dr[-1])
        print("DAILY_FIELDS",sorted(dr[-1].keys()))
        print("DAILY_LAST",json.dumps(dr[-1],ensure_ascii=False))
        if missing:
            raise SystemExit("FAIL missing fields "+repr(sorted(missing)))
        if float(dr[-1]["Trading_Volume"])<=0:
            raise SystemExit("FAIL daily volume")
        print("PASS | Fugle web adapter snapshot + FinMind-shaped daily rows")

if __name__=="__main__":
    main()
