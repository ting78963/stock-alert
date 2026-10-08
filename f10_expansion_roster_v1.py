#!/usr/bin/env python3
"""F10 expansion roster research. Official sources + production SQLite READ ONLY."""
import csv,json,re,sqlite3,time,urllib.request,sys,os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

TWSE="https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX="https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
OUT=Path("/var/data/stock-alert/_f10_expansion_research")
DB=Path("/var/data/stock-alert/f10_baseline_v1.sqlite3")
EXCLUDE={"02","09","14","15","16","17","18","22","32","33","37","38"}
ALLOW_15={"2630","2634","2645"}
ALLOW_08={"1802","1809","1810"}
EXCLUDE_20={"5871","6592","6958","7855","9941","2348","9940","9945","9928","9919"}

def download(url):
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 F10-research"})
            with urllib.request.urlopen(req,timeout=30) as resp: rows=json.load(resp)
            if not isinstance(rows,list) or not rows: raise ValueError("empty official source")
            return rows
        except Exception:
            if attempt==2: raise
            time.sleep(2)

def eligible(code,industry):
    if industry=="01": return code=="1101"
    if industry=="08": return code in ALLOW_08
    if industry=="15": return code in ALLOW_15
    if industry=="20" and code in EXCLUDE_20: return False
    return industry not in EXCLUDE

def main():
    print("[READ ONLY] official sources and production F10 database",flush=True)
    a,b=download(TWSE),download(TPEX)
    if not (1000<=len(a)<=1400 and 750<=len(b)<=1100):
        raise RuntimeError(f"official coverage failed: {len(a)}, {len(b)}")
    da={str(r.get("出表日期","")).strip() for r in a}
    db={str(r.get("Date","")).strip() for r in b}
    if len(da)!=1 or da!=db or not next(iter(da)):
        raise RuntimeError(f"official date mismatch: {da} / {db}")
    official={};invalid=[]
    for market,rows,idkey,namekey,indkey in (
        ("TWSE",a,"公司代號","公司簡稱","產業別"),
        ("TPEX",b,"SecuritiesCompanyCode","CompanyAbbreviation","SecuritiesIndustryCode")
    ):
        for r in rows:
            s=str(r.get(idkey,"")).strip()
            if not re.fullmatch(r"[0-9]{4}",s):
                invalid.append([market,s]);continue
            if s in official: raise RuntimeError("duplicate symbol "+s)
            name=str(r.get(namekey,"")).strip()
            industry=str(r.get(indkey,"")).strip().zfill(2)
            if not name or not re.fullmatch(r"[0-9]{2}",industry):
                raise RuntimeError("invalid identity "+s)
            official[s]=dict(symbol=s,name=name,market=market,industry=industry,eligible=eligible(s,industry))
    if len(official)<1900 or len(invalid)>20 or "5371" in official:
        raise RuntimeError("official identity coverage mismatch")
    if any(not official.get(s,{}).get("eligible") for s in ("1101","1802","1809","1810","2630","2634","2645")):
        raise RuntimeError("allowlist validation failed")
    if not DB.is_file(): raise RuntimeError("production F10 database missing")
    with sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=10) as conn:
        members={str(r[0]) for r in conn.execute("SELECT symbol FROM member")}
        history={str(s):int(n) for s,n in conn.execute("SELECT symbol,COUNT(*) FROM f10_day GROUP BY symbol")}
    if "5371" in members or len(members)!=434 or set(history)-members:
        raise RuntimeError(f"production F10 baseline changed: members={len(members)}")
    allowed={s for s,r in official.items() if r["eligible"]}
    new=sorted(allowed-members)
    kept=sorted(allowed&members)
    outside=sorted(members-allowed)
    if (len(allowed),len(new),len(kept),len(outside))!=(1444,1014,430,4):
        raise RuntimeError(f"snapshot mismatch: eligible={len(allowed)} new={len(new)} kept={len(kept)} outside={len(outside)}")
    if set(new)&set(history): raise RuntimeError("new members already have history")
    report={
        "generated_at":datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
        "official_date_roc":next(iter(da)),
        "status":"DRAFT - no production integration",
        "counts":{"official_raw":len(a)+len(b),"official_4digit":len(official),
                  "non4digit":len(invalid),"eligible":len(allowed),"current_f10":len(members),
                  "new_f10":len(new),"eligible_in_f10":len(kept),
                  "existing_outside_policy":len(outside),"future_f10_preserve_existing":len(members)+len(new)},
        "rules":{"excluded_industries":sorted(EXCLUDE),"allow_15":sorted(ALLOW_15),
                 "allow_08":sorted(ALLOW_08),"allow_01":["1101"],
                 "exclude_20_provisional":sorted(EXCLUDE_20)},
        "new_symbols":new,"existing_outside_policy":outside,"non4digit_records":invalid}
    OUT.mkdir(parents=True,exist_ok=True)
    def write_csv(filename,fields,rows):
        temp=OUT/(filename+".tmp")
        with temp.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        os.replace(temp,OUT/filename)
    allrows=[dict(official[s],in_f10=s in members,historical_days=history.get(s,0),
                  action="ADD" if s in new else ("KEEP" if s in members else "EXCLUDE"))
             for s in sorted(official)]
    write_csv("f10_expansion_official_all_v1.csv",
              ["symbol","name","market","industry","eligible","in_f10","historical_days","action"],allrows)
    write_csv("f10_expansion_add_1014_v1.csv",
              ["symbol","name","market","industry"],
              [{k:official[s][k] for k in ("symbol","name","market","industry")} for s in new])
    tmp=OUT/"f10_expansion_roster_v1.json.tmp"
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,OUT/"f10_expansion_roster_v1.json")
    print("[PASS] "+json.dumps(report["counts"],ensure_ascii=False),flush=True)
    print("[EXISTING OUTSIDE POLICY]",outside,flush=True)
    print("[OUTPUT]",OUT,flush=True)
    print("[NO PRODUCTION WRITE] [NO FUGLE REQUEST]",flush=True)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"[STOP] {type(e).__name__}: {e}",file=sys.stderr,flush=True)
        sys.exit(2)
