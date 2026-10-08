#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F10 staged 1013-member integration. Dry-run default; explicit --apply required.
Never modifies A/B, seeds, holidays, or the existing F10 updater.
"""
import argparse,datetime,json,os,sqlite3,sys
from collections import Counter
from pathlib import Path

ROOT=Path("/var/data/stock-alert")
STAGE=ROOT/"_f10_expansion_research"/"f10_expansion_stage_v1.sqlite3"
ROSTER=ROOT/"_f10_expansion_research"/"f10_expansion_roster_v1.json"
PROD=ROOT/"f10_baseline_v1.sqlite3"
BACKUPS=ROOT/"_f10_expansion_research"/"backups"
EXCLUDED={"1589"}
OLD=434
NEW=1013
TARGET=1447

def stop(msg):raise RuntimeError(msg)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true",help="Back up and atomically integrate; omitted = read-only dry-run")
    args=p.parse_args()
    if not STAGE.is_file() or not ROSTER.is_file() or not PROD.is_file():stop("required files absent")
    roster=json.loads(ROSTER.read_text(encoding="utf-8"))
    expected=set(map(str,roster["new_symbols"]))-EXCLUDED
    if len(expected)!=NEW or EXCLUDED-set(map(str,roster["new_symbols"])):stop("roster count/identity mismatch")
    with sqlite3.connect(f"file:{STAGE}?mode=ro",uri=True) as stage:
        statuses=dict(stage.execute("SELECT symbol,status FROM audit"))
        if set(statuses)!=expected|EXCLUDED or any(statuses[s]!="PASS" for s in expected) or statuses["1589"]!="FAIL":stop("staging audit mismatch")
        counts=dict(stage.execute("SELECT symbol,COUNT(*) FROM f10_day GROUP BY symbol"))
        if set(counts)!=expected or any(not 5<=v<=11 for v in counts.values()):stop("staging day count mismatch")
        day_count=sum(counts.values())
        with sqlite3.connect(f"file:{PROD}?mode=ro",uri=True) as prod_ro:
            existing={r[0] for r in prod_ro.execute("SELECT symbol FROM member")}
            if len(existing)!=OLD or existing&expected:stop("production member count or overlap mismatch")
            existing_days=prod_ro.execute("SELECT COUNT(*) FROM f10_day").fetchone()[0]
            collision=prod_ro.execute("SELECT COUNT(*) FROM f10_day WHERE symbol IN (SELECT symbol FROM member)").fetchone()[0]
            if collision!=existing_days:stop("production has orphan f10_day rows; stop")
            print(f"[PREFLIGHT PASS] production={len(existing)} stage={len(expected)} staged_days={day_count} target={TARGET}",flush=True)
            print(f"[PRESERVE] existing_f10_days={existing_days} excluded=1589",flush=True)
            if not args.apply:
                print("[DRY RUN] NO PRODUCTION WRITE. To integrate, rerun with --apply.",flush=True)
                return
        BACKUPS.mkdir(parents=True,exist_ok=True) if args.apply else None
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup=BACKUPS/f"f10_baseline_before_expansion_{stamp}.sqlite3"
        if backup.exists():stop("backup filename already exists")
        with sqlite3.connect(PROD,timeout=60) as prod:
            prod.execute("PRAGMA busy_timeout=60000")
            # SQLite online backup captures WAL state consistently.
            with sqlite3.connect(backup) as dst:prod.backup(dst)
            with sqlite3.connect(f"file:{backup}?mode=ro",uri=True) as chk:
                if chk.execute("PRAGMA integrity_check").fetchone()[0]!="ok":stop("backup integrity check failed")
                if chk.execute("SELECT COUNT(*) FROM member").fetchone()[0]!=OLD:stop("backup member mismatch")
                if chk.execute("SELECT COUNT(*) FROM f10_day").fetchone()[0]!=existing_days:stop("backup day mismatch")
            print(f"[BACKUP PASS] {backup}",flush=True)
            # Prevent concurrent updater from silently altering membership between preflight and commit.
            prod.execute("BEGIN IMMEDIATE")
            try:
                if prod.execute("SELECT COUNT(*) FROM member").fetchone()[0]!=OLD:stop("concurrent membership change")
                if prod.execute("SELECT COUNT(*) FROM f10_day").fetchone()[0]!=existing_days:stop("concurrent day-count change")
                if prod.execute("SELECT COUNT(*) FROM member WHERE symbol='1589'").fetchone()[0]:stop("1589 unexpectedly present")
                now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds")
                prod.executemany("INSERT INTO member(symbol,added_at,source) VALUES(?,?,?)",((s,now,"f10_expansion_stage_v1") for s in sorted(expected)))
                cursor=stage.execute("SELECT symbol,day,full,pts_json FROM f10_day ORDER BY symbol,day")
                inserted=0
                for row in cursor:
                    prod.execute("INSERT INTO f10_day(symbol,day,full,pts_json) VALUES(?,?,?,?)",row)
                    inserted+=1
                if inserted!=day_count:stop("insert count mismatch")
                if prod.execute("SELECT COUNT(*) FROM member").fetchone()[0]!=TARGET:stop("target member count mismatch")
                if prod.execute("SELECT COUNT(*) FROM f10_day").fetchone()[0]!=existing_days+day_count:stop("target day count mismatch")
                if prod.execute("SELECT COUNT(*) FROM member WHERE symbol='1589'").fetchone()[0]:stop("1589 must remain excluded")
                if prod.execute("SELECT COUNT(*) FROM member WHERE source='f10_expansion_stage_v1'").fetchone()[0]!=NEW:stop("new source count mismatch")
                prod.commit()
            except BaseException:
                prod.rollback()
                raise
        with sqlite3.connect(f"file:{PROD}?mode=ro",uri=True) as verify:
            if verify.execute("PRAGMA integrity_check").fetchone()[0]!="ok":stop("post-commit SQLite integrity check failed")
            if verify.execute("SELECT COUNT(*) FROM member").fetchone()[0]!=TARGET:stop("post-commit member mismatch")
            if verify.execute("SELECT COUNT(*) FROM f10_day").fetchone()[0]!=existing_days+day_count:stop("post-commit day mismatch")
        print(f"[INTEGRATION PASS] members={TARGET} newly_added={NEW} day_rows_added={day_count}",flush=True)
        print(f"[ROLLBACK BACKUP] {backup}",flush=True)
        print("[NO A/B CODE CHANGE] [NO F10 CALCULATION CHANGE]",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print(f"[STOP] {type(e).__name__}: {e}",file=sys.stderr,flush=True)
        sys.exit(2)
