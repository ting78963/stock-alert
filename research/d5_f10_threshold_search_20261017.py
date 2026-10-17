#!/usr/bin/env python3
"""Isolated F10 D5 search. Standard library only; no network or production imports.

Use --self-test offline. Real run: --db --mother --sessions --out.
Sessions JSON: {"source": "verified calendar reference", "sessions": [ISO dates]}.
No absent bar, stock-day or session is imputed. Only complete 09:00..13:30
curves are admissible. Incomplete cohorts emit audit only, never rankings.
F10 is a derived archive (producer coerces missing volume to zero); internal
consistency cannot establish original API completeness or live availability.
Results are conditional volume comparisons, never B recognition or handoffs.
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
import re
import sqlite3
import statistics
import tempfile
import unittest
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

START='2026-10-01'; END='2026-10-15'; TEST='2026-10-16'
OLD=((541,4000),(550,2000))
GRIDS=((541,550,560,570,580),(541,555,570,600))

class AuditError(ValueError): pass

def check(ok,message):
    if not ok: raise AuditError(message)

def clock(s):
    check(isinstance(s,str) and re.fullmatch(r'\d{2}:\d{2}(:00)?',s),'INVALID_MINUTE')
    h,m=map(int,s[:5].split(':')); t=h*60+m
    check(0<=m<60 and 540<=t<=810,'MINUTE_OUTSIDE_SESSION')
    return t

def hhmm(t): return f'{t//60:02d}:{t%60:02d}'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def parse_curve(full,text):
    check(type(full) in (int,float) and math.isfinite(full) and full>0,'INVALID_FULL')
    points=json.loads(text); check(isinstance(points,list) and points,'EMPTY_POINTS')
    curve={}; previous=-1; cumulative=0.0
    for point in points:
        check(isinstance(point,list) and len(point)==2,'INVALID_POINT')
        t=clock(point[0]); v=point[1]
        check(t>previous,'DUPLICATE_OR_UNORDERED_MINUTE')
        check(type(v) in (int,float) and math.isfinite(v) and v>=cumulative,'INVALID_CUMULATIVE')
        curve[t]=float(v); previous=t; cumulative=v
    check(abs(cumulative-full)<=max(.0001,full*1e-9),'FULL_MISMATCH')
    missing=[hhmm(t) for t in range(540,811) if t not in curve]
    return curve,missing

def read_inputs(db,mother,sessions):
    check(db.is_file(),'DB_NOT_FOUND')
    # Explicit read-only transaction, no production db() helpers, no DDL/checkpoint.
    with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.execute('PRAGMA query_only=ON'); con.execute('BEGIN')
        members=[r[0] for r in con.execute('SELECT symbol FROM member ORDER BY symbol')]
        rows=con.execute('SELECT symbol,day,full,pts_json FROM f10_day WHERE day>=? AND day<=? ORDER BY day,symbol',(START,TEST)).fetchall()
    check(members and len(members)==len(set(members)) and all(isinstance(s,str) and re.fullmatch(r'\d{4}',s) for s in members),'INVALID_MEMBERS')
    raw=mother.read_bytes(); m=json.loads(raw.decode('utf-8-sig'))
    ids=m.get('stock_ids'); check(m.get('date')==TEST and isinstance(ids,list),'MOTHER_IDENTITY')
    check(all(isinstance(s,str) and re.fullmatch(r'\d{4}',s) for s in ids) and len(ids)==len(set(ids)) and type(m.get('count')) is int and m['count']==len(ids),'MOTHER_COUNT_OR_IDS')
    calendar_raw=sessions.read_bytes(); cal=json.loads(calendar_raw.decode('utf-8-sig'))
    days=cal.get('sessions'); check(isinstance(cal.get('source'),str) and cal['source'].strip() and isinstance(days,list) and days,'CALENDAR_SOURCE_REQUIRED')
    check(all(isinstance(d,str) and date.fromisoformat(d).isoformat()==d for d in days) and days==sorted(set(days)),'INVALID_SESSION_LIST')
    train=[d for d in days if START<=d<=END]; check(len(train)>=4 and TEST in days,'INSUFFICIENT_CALENDAR')
    wanted=set(train+[TEST]); check(all(d in wanted for _,d,_,_ in rows),'DATABASE_DATE_NOT_IN_CALENDAR')
    audit=dict(db=str(db),source_rows_sha256=digest(rows),member_sha256=digest(members),input_row_count=len(rows),excluded_4906_rows=sum(s=='4906' for s,_,_,_ in rows),mother_sha256=hashlib.sha256(raw).hexdigest(),
        calendar_sha256=hashlib.sha256(calendar_raw).hexdigest(),calendar_source=cal['source'],
        source_limit='F10 derived cumulative archive; original null-to-zero coercion cannot be independently verified',
        time_policy='Fugle minute labels; completion M+1 is a model, NOT proven arrival',
        excluded_stock='4906',issues=[],cohorts={})
    parsed={}; seen=set()
    for sid,d,full,text in rows:
        key=(d,sid); check(key not in seen,'DUPLICATE_STOCK_DAY'); seen.add(key)
        check(sid in members,'ROW_OUTSIDE_MEMBER')
        if sid=='4906': continue
        try:
            curve,missing=parse_curve(full,text)
            if missing:
                audit['issues'].append(dict(date=d,stock_id=sid,reason='UNKNOWN_MISSING_MINUTES',missing_minutes=missing,row_sha256=digest([sid,d,full,text])))
            else: parsed[key]=curve
        except (ValueError,TypeError) as ex:
            audit['issues'].append(dict(date=d,stock_id=sid,reason=str(ex),row_sha256=digest([sid,d,full,text])))
    universes={'ALL_F10':set(members)-{'4906'},'A_MOTHER_1016':set(ids)-{'4906'}}
    for name,symbols in universes.items():
        # A mother is used solely for 10/16 descriptive validation, never training selection.
        cohort_days=train+[TEST] if name=='ALL_F10' else [TEST]
        missing=[dict(date=d,stock_id=s) for d in cohort_days for s in sorted(symbols) if (d,s) not in parsed]
        audit['cohorts'][name]=dict(symbols=sorted(symbols),days=cohort_days,unusable_stock_days=missing,
            status='COMPLETE_INTERNAL_ARCHIVE' if symbols and not missing else 'BLOCKED_INCOMPLETE')
    return parsed,train,universes,audit

def threshold(rule,t): return next((v for start,v in reversed(rule) if t>=start),None)

def first_hit(curve,rule,completed=False):
    for decision in range(541,811):
        label=decision-int(completed)
        check(label in curve,'MISSING_MINUTE_NO_IMPUTATION')
        if curve[label]>=threshold(rule,decision): return decision
    return None

def quantile(values,q):
    values=sorted(values); position=(len(values)-1)*q; lo=int(position); hi=math.ceil(position)
    return values[lo]+(values[hi]-values[lo])*(position-lo)

def generate_candidates(records,fit_days):
    check(records and all(d in fit_days and START<=d<=END for d,_,_ in records),'TRAINING_LEAKAGE')
    # Data-derived volume scale: empirical opening cumulative distribution.
    # Quantile ranks and time grids are search design, not fixed lot thresholds.
    pool=[curve[550] for _,_,curve in records]
    rules={}
    for grid,high,low in itertools.product(GRIDS,(.5,.75,.9),(0,.25,.5)):
        if low>high: continue
        values=[quantile(pool,high+(low-high)*i/(len(grid)-1)) for i in range(len(grid))]
        if min(values)<=0: continue
        rule=tuple(zip(grid,values)); rules[digest(rule)[:12]]=rule
    check(rules,'NO_POSITIVE_DATA_DERIVED_CANDIDATES')
    return rules

def metrics(records,rule,completed):
    counts=Counter(); arrivals=Counter(); old_arrivals=Counter(); deltas=[]; by_day={}; stocks={k:set() for k in ('delayed','lost','extra','early5','early10','early20')}
    for day,sid,curve in records:
        old=first_hit(curve,OLD,completed); new=first_hit(curve,rule,completed)
        counts['stock_days']+=1
        if old is not None: old_arrivals[(day,old)]+=1
        if new is not None: arrivals[(day,new)]+=1
        if old is None and new is None: counts['neither']+=1
        elif old is None:
            counts['extra_candidates']+=1; stocks['extra'].add(sid)
        elif new is None:
            counts['lost_candidates']+=1; stocks['lost'].add(sid)
        else:
            delta=old-new; deltas.append(delta)
            counts['same' if delta==0 else 'earlier' if delta>0 else 'delayed']+=1
            if delta<0: stocks['delayed'].add(sid)
            for n in (5,10,20):
                counts[f'early_ge_{n}']+=int(delta>=n)
                if delta>=n: stocks[f'early{n}'].add(sid)
    check(sum(counts[k] for k in ('neither','extra_candidates','lost_candidates','same','earlier','delayed'))==len(records),'PARTITION_ERROR')
    days=sorted({d for d,_,_ in records})
    for d in days:
        peak=max((arrivals[(d,t)] for t in range(541,811)),default=0)
        old_peak=max((old_arrivals[(d,t)] for t in range(541,811)),default=0)
        by_day[d]=dict(candidate_peak=peak,old_peak=old_peak,
            peak_minutes=[hhmm(t) for t in range(541,811) if peak and arrivals[(d,t)]==peak])
    return dict(**{k:counts[k] for k in ('stock_days','neither','extra_candidates','lost_candidates','same','earlier','delayed','early_ge_5','early_ge_10','early_ge_20')},
        unique_stocks=len({s for _,s,_ in records}),distinct_stock_counts={k:len(v) for k,v in stocks.items()},stock_ids_by_effect={k:sorted(v) for k,v in stocks.items()},paired_n=len(deltas),paired_median_minutes=statistics.median(deltas) if deltas else None,
        peak_single_minute=max((v['candidate_peak'] for v in by_day.values()),default=0),peaks_by_day=by_day,
        arrivals=[dict(date=d,minute=hhmm(t),count=n,old_count=old_arrivals[(d,t)]) for (d,t),n in sorted({key:arrivals[key] for key in set(arrivals)|set(old_arrivals)}.items())])

def pareto(scores):
    def vector(m): return (-m['early_ge_10'],m['delayed']+m['lost_candidates'],m['extra_candidates'],m['peak_single_minute'])
    selected=[]
    for name,m in scores.items():
        v=vector(m)
        if not any(all(a<=b for a,b in zip(vector(other),v)) and any(a<b for a,b in zip(vector(other),v)) for k,other in scores.items() if k!=name): selected.append(name)
    return sorted(selected)

def run(db,mother,sessions):
    parsed,train,universes,audit=read_inputs(db,mother,sessions)
    report=dict(version=1,status='AUDIT_ONLY',audit=audit,candidates={},comparisons=[],
        limits=['VOLUME_ONLY_NOT_B_ELIGIBILITY_OR_A_HANDOFF','NOT_PROVEN_API_AVAILABILITY','NO_ZERO_FILL',
                'ARCHIVE_MEMBER_SURVIVORSHIP_AND_1016_MOTHER_SELECTION_BIAS','NO_TRUE_OPTIMUM_WITHOUT_SIGNAL_QUALITY_AND_LOAD_BUDGET'])
    def records(days,symbols): return [(d,s,parsed[(d,s)]) for d in days for s in sorted(symbols)]
    all_symbols=universes['ALL_F10']
    # Completeness per split: training failure blocks search; test failure does not erase training.
    if any((d,s) not in parsed for d in train for s in all_symbols):
        report['status']='BLOCKED_TRAINING_COVERAGE'; return report
    fit_days=train[:-2]; tuning_days=train[-2:]
    fit=records(fit_days,all_symbols); tune=records(tuning_days,all_symbols)
    candidates=generate_candidates(fit,fit_days)
    report['candidates']={k:[[hhmm(t),v] for t,v in rule] for k,rule in candidates.items()}
    report['freeze']=dict(fit_days=fit_days,tuning_days=tuning_days,validation_day=TEST,
        candidate_sha256=digest(report['candidates']),fit_input_sha256=digest(fit),tuning_input_sha256=digest(tune),selection='Pareto on training holdout M+1 only: maximize early>=10, minimize delayed+lost, extra, peak')
    tuning={k:metrics(tune,rule,True) for k,rule in candidates.items()}
    report['freeze']['shortlist']=pareto(tuning)
    # Frozen selection above never reads validation volume, metrics or mother membership.
    phases=[('FIT',fit_days,all_symbols,'ALL_F10'),('TRAIN_HOLDOUT',tuning_days,all_symbols,'ALL_F10'),
            ('TRAIN_ALL',train,all_symbols,'ALL_F10')]
    for cohort,symbols in universes.items():
        if symbols and all((TEST,s) in parsed for s in symbols): phases.append(('VALIDATION_1016',[TEST],symbols,cohort))
    for phase,days,symbols,cohort in phases:
        for name,rule in [('OLD',OLD)]+list(candidates.items()):
            for completed in (False,True):
                report['comparisons'].append(dict(phase=phase,cohort=cohort,candidate=name,model='M_PLUS_1' if completed else 'MINUTE_LABEL',
                    shortlisted=name in report['freeze']['shortlist'],**metrics(records(days,symbols),rule,completed)))
    report['status']='CONDITIONAL_ARCHIVE_COMPARISON_ONLY'
    return report

def write_report(out,report):
    # New directory only; never write within a production data tree.
    check('/var/data' not in out.resolve().as_posix(),'OUTPUT_MUST_BE_OUTSIDE_PRODUCTION_DATA')
    out.mkdir(parents=True,exist_ok=False)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'candidates.csv').open('x',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['candidate','shortlisted','schedule']); writer.writeheader()
        for name,rule in report.get('candidates',{}).items():
            writer.writerow(dict(candidate=name,shortlisted=name in report.get('freeze',{}).get('shortlist',[]),schedule=json.dumps(rule)))
    fields=['phase','cohort','candidate','model','shortlisted','stock_days','unique_stocks','early_ge_5','early_ge_10','early_ge_20','delayed','lost_candidates','extra_candidates','same','earlier','neither','paired_n','paired_median_minutes','peak_single_minute']
    with (out/'comparison.csv').open('x',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        writer.writerows({k:r[k] for k in fields} for r in report.get('comparisons',[]))

def self_test():
    class Tests(unittest.TestCase):
        def curve(self,v): return {t:float(v) for t in range(540,811)}
        def test_missing_not_filled(self):
            text=json.dumps([[hhmm(t),2000] for t in range(540,811) if t!=550])
            curve,missing=parse_curve(2000,text); self.assertEqual(missing,['09:10'])
            with self.assertRaises(AuditError): first_hit(curve,OLD)
        def test_integrity(self):
            for points,full in [([['09:00',1],['09:00',1]],1),([['09:00',2],['09:01',1]],1),([['09:00:01',1]],1),([['09:00',float('nan')]],1),([['09:00',1]],2)]:
                with self.assertRaises(AuditError): parse_curve(full,json.dumps(points))
        def test_boundaries(self):
            self.assertEqual(first_hit(self.curve(4000),OLD),541)
            self.assertEqual(first_hit(self.curve(2000),OLD),550)
            self.assertEqual(first_hit(self.curve(2000),OLD,True),550)
            c=self.curve(0); c.update({t:4000 for t in range(550,811)})
            self.assertEqual(first_hit(c,OLD),550); self.assertEqual(first_hit(c,OLD,True),551)
        def test_no_test_day_candidate_generation(self):
            with self.assertRaises(AuditError): generate_candidates([(TEST,'1234',self.curve(2000))],[TEST])
            self.assertEqual(generate_candidates([(START,'1234',self.curve(2000))],[START]),generate_candidates([(START,'1234',self.curve(2000))],[START]))
        def test_metrics(self):
            records=[(START,'1234',self.curve(2000))]
            m=metrics(records,((541,2000),),False)
            self.assertEqual(m['early_ge_5'],1); self.assertEqual(m['early_ge_10'],0)
            self.assertEqual(m['paired_median_minutes'],9); self.assertEqual(m['peak_single_minute'],1)
            self.assertEqual(metrics(records,((541,3000),),False)['lost_candidates'],1)
            self.assertEqual(metrics([(START,'1234',self.curve(1500))],((541,1000),),False)['extra_candidates'],1)
        def fixture(self,root):
            db=root/'input.sqlite'; days=['2026-10-01','2026-10-02','2026-10-05','2026-10-06',TEST]
            with closing(sqlite3.connect(db)) as con, con:
                con.execute('CREATE TABLE member(symbol TEXT)'); con.execute("INSERT INTO member VALUES ('1234')")
                con.execute('CREATE TABLE f10_day(symbol TEXT,day TEXT,full REAL,pts_json TEXT)')
                for d in days: con.execute('INSERT INTO f10_day VALUES (?,?,?,?)',('1234',d,2000,json.dumps([[hhmm(t),2000] for t in range(540,811)])))
            mother=root/'mother.json'; mother.write_text(json.dumps(dict(date=TEST,stock_ids=['1234','4906'],count=2)))
            sessions=root/'sessions.json'; sessions.write_text(json.dumps(dict(source='synthetic only',sessions=days)))
            return db,mother,sessions
        def test_integration_readonly_and_frozen(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); inputs=self.fixture(root); before=inputs[0].read_bytes()
                r=run(*inputs); self.assertTrue(r['comparisons']); self.assertEqual(inputs[0].read_bytes(),before)
                with closing(sqlite3.connect(inputs[0])) as con, con: con.execute('UPDATE f10_day SET full=9000,pts_json=? WHERE day=?',(json.dumps([[hhmm(t),9000] for t in range(540,811)]),TEST))
                other=run(*inputs); self.assertEqual(r['freeze'],other['freeze']); self.assertEqual(r['candidates'],other['candidates'])
                write_report(root/'out',r)
                with self.assertRaises(FileExistsError): write_report(root/'out',r)
        def test_incomplete_blocks(self):
            with tempfile.TemporaryDirectory() as tmp:
                inputs=self.fixture(Path(tmp))
                with closing(sqlite3.connect(inputs[0])) as con, con: con.execute('DELETE FROM f10_day WHERE day=?',(START,))
                r=run(*inputs); self.assertEqual(r['status'],'BLOCKED_TRAINING_COVERAGE'); self.assertFalse(r['comparisons'])
        def test_advance_buckets_delay_and_peak(self):
            c=self.curve(1000); c.update({t:2000 for t in range(580,811)})
            m=metrics([(START,'1234',c),(START,'5678',c)],((541,1000),),False)
            self.assertEqual([m[f'early_ge_{n}'] for n in (5,10,20)],[2,2,2])
            self.assertEqual(m['distinct_stock_counts']['early20'],2)
            self.assertEqual(m['peak_single_minute'],2)
            delayed=metrics([(START,'1234',self.curve(4000))],((541,5000),(570,4000)),False)
            self.assertEqual(delayed['delayed'],1); self.assertEqual(delayed['stock_ids_by_effect']['delayed'],['1234'])
        def test_test_missing_does_not_reselect(self):
            with tempfile.TemporaryDirectory() as tmp:
                inputs=self.fixture(Path(tmp)); valid=run(*inputs)
                with closing(sqlite3.connect(inputs[0])) as con, con:
                    con.execute('DELETE FROM f10_day WHERE day=?',(TEST,))
                r=run(*inputs)
                self.assertEqual(valid['freeze'],r['freeze'])
                self.assertFalse(any(row['phase']=='VALIDATION_1016' for row in r['comparisons']))
                self.assertEqual(r['audit']['cohorts']['A_MOTHER_1016']['status'],'BLOCKED_INCOMPLETE')
        def test_pareto(self):
            good=dict(early_ge_10=10,delayed=0,lost_candidates=0,extra_candidates=0,peak_single_minute=1)
            bad=dict(good,early_ge_10=0)
            self.assertEqual(pareto({'good':good,'bad':bad}),['good'])
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if result.wasSuccessful() else 1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-test',action='store_true'); p.add_argument('--db',type=Path)
    p.add_argument('--mother',type=Path); p.add_argument('--sessions',type=Path); p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.self_test: return self_test()
    if any(v is None for v in (a.db,a.mother,a.sessions,a.out)): p.error('--db --mother --sessions --out are required')
    check(a.out.resolve() not in {v.resolve() for v in (a.db,a.mother,a.sessions)}, 'OUTPUT_MUST_NOT_REPLACE_INPUT')
    try: report=run(a.db,a.mother,a.sessions)
    except (AuditError,OSError,sqlite3.Error,ValueError,TypeError) as ex: report=dict(status='BLOCKED_INPUT_AUDIT',error=str(ex),comparisons=[])
    write_report(a.out,report); print(report['status'],a.out)
    return 2 if report['status'].startswith('BLOCKED') else 0

if __name__=='__main__': raise SystemExit(main())
