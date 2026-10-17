#!/usr/bin/env python3
"""F15 D5 v2: offline archive audit and volume-only comparison. No network/import side effects.

Schema checked against f15_trajectory_store.py / f15_eod_signal_report.py.
Minute M completion at M+1 follows B completed_cutoff; this is a MODEL,
not evidence of historical arrival. No actual handoff/availability conclusions.
Missing rows are never filled. Explicit volume=0 rows are observed zero volume;
the archive schema has no evidence mechanism proving an absent row was zero.
"""
import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

BRANCH = 'research/f15-d5-volume-replay-20261017'
SCHEMA = 'f15_trajectory_v1'
RULES = {'OLD': [(541,4000),(550,2000)],
         'D5': [(541,4000),(550,1700),(560,1400),(570,1100),(580,1000)],
         'FIX1000': [(541,1000)], 'FIX1500': [(541,1500)], 'FIX2000': [(541,2000)]}
CATEGORIES = ('SAME','EARLY_1_TO_29','EARLY_30_PLUS',
              'D5_ONLY_BY_RECOGNITION_LABEL','NO_D5')

class AuditError(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise AuditError(reason)

def tm(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}(:00)?', value),
            'INVALID_OR_NON_MINUTE_TIME: ' + repr(value))
    h, m = map(int, value[:5].split(':'))
    require(0 <= m < 60 and 540 <= h*60+m <= 810, 'TIME_OUTSIDE_SESSION')
    return h*60+m

def fmt(value):
    return None if value is None else f'{value//60:02d}:{value%60:02d}'

def number(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'INVALID_NONNEGATIVE_VOLUME')
    return float(value)

def hit(bars, rule, cutoff, completed=False):
    """Label comparison or conservative completed-bar model by recognition clock.

    Threshold is evaluated at the model decision clock, including threshold drops.
    Completion model can use 09:00 volume at 09:01. No missing bars are synthesized.
    """
    for label, cumulative in bars:
        decision = label + int(completed)
        if decision < 541 or decision > cutoff:
            continue
        threshold = next((v for start,v in reversed(rule) if decision >= start), None)
        if threshold is not None and cumulative >= threshold:
            return decision
    return None

def classify(old, d5):
    require(old is None or (d5 is not None and d5 <= old), 'MONOTONICITY_FAILURE')
    if d5 is None:
        return 'NO_D5', None
    if old is None:
        return 'D5_ONLY_BY_RECOGNITION_LABEL', None
    delta = old-d5
    return ('SAME' if delta == 0 else 'EARLY_1_TO_29' if delta < 30
            else 'EARLY_30_PLUS'), delta

def manifest_audit(day, manifest, actual):
    require(isinstance(manifest, dict), 'MANIFEST_NOT_OBJECT')
    require(manifest.get('schema') == SCHEMA and manifest.get('date') == day,
            'MANIFEST_SCHEMA_OR_DATE')
    names = manifest.get('files')
    require(isinstance(names, list) and all(isinstance(n,str) and
            re.fullmatch(r'\d{4}_(P1|A|B|C)_\d{4}\.json', n) for n in names),
            'MANIFEST_FILENAMES')
    require(len(set(names)) == len(names), 'MANIFEST_DUPLICATES')
    require(type(manifest.get('count')) is int and manifest['count'] == len(names),
            'MANIFEST_COUNT')
    require(set(names) == set(actual), 'MANIFEST_FILE_SET_MISMATCH')
    require(bool(names), 'EMPTY_MANIFEST')

def record_audit(day, filename, x):
    require(isinstance(x, dict) and x.get('schema') == SCHEMA, 'RECORD_SCHEMA')
    i = x.get('identity'); e = x.get('production_event_snapshot'); a = x.get('causal_anchor')
    require(all(isinstance(z,dict) for z in (i,e,a)), 'MISSING_IDENTITY_EVENT_ANCHOR')
    sid, cls = i.get('stock_id'), i.get('signal_class')
    require(isinstance(sid,str) and re.fullmatch(r'\d{4}',sid) and cls in ('P1','A','B','C'),
            'INVALID_SIGNAL_IDENTITY')
    rec = tm(i.get('recognition_time')); disc = tm(a.get('discovered_at'))
    require(i.get('date') == day and filename == f'{sid}_{cls}_{fmt(rec).replace(":", "")}.json',
            'IDENTITY_DATE_OR_FILENAME')
    require(e.get('schema') == ('b_signal_event_v2' if cls == 'P1' else 'b_signal_event_v1'),
            'EVENT_SCHEMA')
    require(e.get('date') == day and str(e.get('stock_id','')).zfill(4) == sid
            and e.get('signal_class') == cls and tm(e.get('recognition_time')) == rec,
            'EVENT_IDENTITY_MISMATCH')
    require(e.get('source') == 'Fugle' and e.get('line_sent') is True,
            'EVENT_SOURCE_OR_DELIVERY_UNVERIFIED')
    require(tm(e.get('discovered_at')) == disc, 'DISCOVERY_MISMATCH')
    require(tm(e.get('live_known_time')) == max(rec,disc), 'LIVE_KNOWN_MISMATCH')
    require(tm(e.get('signal_emitted_at_feed_through')) >= rec, 'FEED_THROUGH_BEFORE_RECOGNITION')
    require(type(e.get('late_discovery')) is bool and e['late_discovery'] == (disc > rec)
            and a.get('late_discovery') == e['late_discovery'], 'LATE_DISCOVERY_MISMATCH')
    require(a.get('delay_seconds') == (max(0,disc-rec)*60), 'DELAY_MISMATCH')
    raw = x.get('trajectory_raw_1m')
    require(isinstance(raw,list) and raw, 'MISSING_BARS')
    bars=[]; cumulative=0.0; last=539; zeros=[]
    for b in raw:
        require(isinstance(b,dict), 'INVALID_BAR')
        t=tm(b.get('minute')); v=number(b.get('volume')); reported=number(b.get('cum_volume'))
        require(t > last, 'DUPLICATE_OR_UNORDERED_BAR')
        cumulative += v
        require(abs(cumulative-reported) <= max(.1,cumulative*.0001), 'CUMULATIVE_MISMATCH')
        bars.append((t,cumulative)); last=t
        if v == 0:
            zeros.append(fmt(t))
    present={t for t,_ in bars}
    missing=[t for t in range(540,rec+1) if t not in present]
    return dict(identity=i, recognition_label=fmt(rec), discovered_at=fmt(disc),
                event_live_known_time=fmt(max(rec,disc)),
                recognition_bar_complete_model=fmt(rec+1),
                first_bar=fmt(bars[0][0]), last_bar=fmt(bars[-1][0]),
                missing_open=[fmt(t) for t in missing if t < bars[0][0]],
                missing_internal=[fmt(t) for t in missing if bars[0][0] <= t <= bars[-1][0]],
                missing_tail=[fmt(t) for t in missing if t > bars[-1][0]],
                observed_zero_volume_minutes=zeros, proven_zero_absent_minutes=[],
                unknown_missing_minutes=[fmt(t) for t in missing], bars=bars)

def compare(record):
    bars=record['bars']; cutoff=tm(record['recognition_label'])
    label={k:hit(bars,v,cutoff) for k,v in RULES.items()}
    complete={k:hit(bars,v,cutoff,True) for k,v in RULES.items()}
    category,delta=classify(label['OLD'], label['D5'])
    # Completion model is separate; never relabel it as actual availability.
    complete_category,complete_delta=classify(complete['OLD'],complete['D5'])
    if complete_category == 'D5_ONLY_BY_RECOGNITION_LABEL':
        complete_category = 'D5_ONLY_BY_RECOGNITION_CLOCK_MODEL'
    return dict(category=category, advance_label_minutes=delta,
                label_hits={k:fmt(v) for k,v in label.items()},
                completed_bar_model_hits={k:fmt(v) for k,v in complete.items()},
                completed_bar_model_category=complete_category,
                completed_bar_model_advance_minutes=complete_delta)

def load(path):
    data=path.read_bytes()
    return json.loads(data.decode('utf-8')), hashlib.sha256(data).hexdigest()

def audit(root):
    result=dict(version=2, scope='ARCHIVED_F15_DELIVERED_SIGNALS_VOLUME_ONLY',
                source_status='ARCHIVE_INTERNAL_CONSISTENCY_ONLY',
                rule_spec_status='IMPLEMENTED_SCHEDULE_ONLY_NO_INDEPENDENT_D5_SPEC',
                independent_source_completeness='UNVERIFIED_NO_RAW_API_OR_EXTERNAL_EVENT_INVENTORY',
                actual_availability_conclusion='BLOCKED_NO_ARRIVAL_OR_REVISION_PROVENANCE',
                handoff_conclusion='BLOCKED_NOT_AN_A_REPLAY',
                time_policy='LABEL <= recognition; completion MODEL M+1 <= recognition clock; thresholds at decision clock',
                files=[], manifests=[], exclusions=[], eligible=[], blocking_errors=[])
    def failure(path, reason):
        result['blocking_errors'].append(dict(path=str(path),reason=str(reason)))
    days=sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith('20'))
    require(bool(days), 'NO_DAYS')
    seen=set()
    for day in days:
        try:
            require(date.fromisoformat(day.name).isoformat() == day.name, 'INVALID_DAY')
            m,digest=load(day/'manifest.json')
            actual={p.name for p in day.glob('*.json') if p.name != 'manifest.json'}
            manifest_audit(day.name,m,actual)
            result['manifests'].append(dict(path=str(day/'manifest.json'),sha256=digest,status='INTERNAL_PASS'))
        except (ValueError,OSError,TypeError) as ex:
            failure(day,ex)
            # Still audit every present record and preserve its exclusion details.
        for p in sorted(day.glob('*.json')):
            if p.name == 'manifest.json':
                continue
            entry=dict(path=str(p), date=day.name)
            try:
                x,digest=load(p); entry.update(sha256=digest,identity=x.get('identity') if isinstance(x,dict) else None)
                r=record_audit(day.name,p.name,x)
                key=(day.name,r['identity']['stock_id'],r['identity']['signal_class'],r['recognition_label'])
                require(key not in seen, 'DUPLICATE_IDENTITY'); seen.add(key)
                entry.update({k:v for k,v in r.items() if k != 'bars'})
                reasons=[]
                if r['unknown_missing_minutes']:
                    reasons.append('UNKNOWN_MISSING_MINUTES')
                if r['identity']['stock_id'] == '4906':
                    reasons.append('POLICY_EXCLUDE_4906')
                if reasons:
                    entry['reasons']=reasons; result['exclusions'].append(entry)
                else:
                    result['eligible'].append(dict(**entry, **compare(r)))
            except (ValueError,OSError,TypeError,KeyError) as ex:
                entry['reasons']=[str(ex)]; result['exclusions'].append(entry)
                failure(p,ex)
            result['files'].append(entry)
    # No cohort statistics at all if source membership/identity validation failed.
    if result['blocking_errors']:
        result['status']='BLOCKED_SOURCE_AUDIT'; result['eligible']=[]
    else:
        result['status']=('AUDITED_SUBSET_LABEL_COMPARISON_ONLY' if result['eligible']
                          else 'NO_ELIGIBLE_SIGNALS_NO_COMPARISON')
        counts=Counter(r['category'] for r in result['eligible'])
        deltas=[r['advance_label_minutes'] for r in result['eligible'] if r['advance_label_minutes'] is not None]
        result['summary']=dict(counts={k:counts[k] for k in CATEGORIES},
            eligible=len(result['eligible']),excluded=len(result['exclusions']),
            paired_n=len(deltas), paired_median_label_advance_including_same=statistics.median(deltas) if deltas else None)
        require(sum(counts.values()) == len(result['eligible']), 'CATEGORY_PARTITION_FAILURE')
    return result

def self_test():
    import tempfile
    import unittest
    class Tests(unittest.TestCase):
        def fixture(self):
            i=dict(date='2026-10-13',stock_id='5230',signal_class='B',recognition_time='09:10')
            e=dict(i,schema='b_signal_event_v1',discovered_at='09:12:00',live_known_time='09:12:00',
                   signal_emitted_at_feed_through='09:10:00',source='Fugle',line_sent=True,late_discovery=True)
            return dict(schema=SCHEMA,identity=i,production_event_snapshot=e,
                causal_anchor=dict(discovered_at='09:12:00',late_discovery=True,delay_seconds=120),
                trajectory_raw_1m=[dict(minute=fmt(t),volume=0,cum_volume=0) for t in range(540,551)])
        def test_switches(self):
            for t,threshold in RULES['D5']:
                self.assertEqual(hit([(t,threshold)],RULES['D5'],t),t)
                self.assertIsNone(hit([(t,threshold-1)],RULES['D5'],t))
            self.assertIsNone(hit([(540,9000)],RULES['D5'],540))
            self.assertEqual(hit([(549,1800),(550,1800)],RULES['D5'],550),550)
        def test_time_and_completion(self):
            for bad in ('09:10:59','09:10junk','09:60','08:59',None):
                with self.assertRaises(AuditError): tm(bad)
            self.assertEqual(tm('09:10:00'),550)
            self.assertIsNone(hit([(550,1700)],RULES['D5'],550,True))
            self.assertEqual(hit([(549,1700)],RULES['D5'],550,True),550)
            self.assertIsNone(hit([(551,9000)],RULES['D5'],550))
            self.assertEqual(hit([(540,4000)],RULES['OLD'],541,True),541)
            for boundary,threshold in RULES['D5'][1:]:
                self.assertIsNone(hit([(boundary-2,threshold)],RULES['D5'],boundary-1,True))
                self.assertEqual(hit([(boundary-1,threshold)],RULES['D5'],boundary,True),boundary)
        def test_5230_open_gap_and_zero(self):
            x=self.fixture(); x['trajectory_raw_1m']=x['trajectory_raw_1m'][2:]
            r=record_audit('2026-10-13','5230_B_0910.json',x)
            self.assertEqual(r['missing_open'],['09:00','09:01'])
            self.assertEqual(r['missing_tail'],[])
            self.assertEqual(r['proven_zero_absent_minutes'],[])
            self.assertEqual(len(record_audit('2026-10-13','5230_B_0910.json',self.fixture())['observed_zero_volume_minutes']),11)
        def test_internal_tail_and_cumulative(self):
            x=self.fixture(); del x['trajectory_raw_1m'][3]
            self.assertEqual(record_audit('2026-10-13','5230_B_0910.json',x)['missing_internal'],['09:03'])
            x=self.fixture(); x['trajectory_raw_1m'].pop()
            self.assertEqual(record_audit('2026-10-13','5230_B_0910.json',x)['missing_tail'],['09:10'])
            for value in (-1,float('nan'),True):
                x=self.fixture(); x['trajectory_raw_1m'][0]['volume']=value
                with self.assertRaises(AuditError): record_audit('2026-10-13','5230_B_0910.json',x)
            x=self.fixture(); x['trajectory_raw_1m'][0]['cum_volume']=1
            with self.assertRaises(AuditError): record_audit('2026-10-13','5230_B_0910.json',x)
        def test_identity_manifest(self):
            m=dict(schema=SCHEMA,date='2026-10-13',files=['5230_B_0910.json'],count=1)
            manifest_audit('2026-10-13',m,set(m['files']))
            for bad in (dict(m,count=2),dict(m,files=m['files']*2,count=2),dict(m,date='2026-10-14')):
                with self.assertRaises(AuditError): manifest_audit('2026-10-13',bad,set(m['files']))
            with self.assertRaises(AuditError): manifest_audit('2026-10-13',m,set())
            x=self.fixture(); x['production_event_snapshot']['stock_id']='9999'
            with self.assertRaises(AuditError): record_audit('2026-10-13','5230_B_0910.json',x)
        def test_more_source_failures(self):
            for field,value in [('source','other'),('line_sent',False),
                                ('live_known_time','09:10'),('late_discovery',False),
                                ('signal_emitted_at_feed_through','09:09')]:
                x=self.fixture(); x['production_event_snapshot'][field]=value
                with self.assertRaises(AuditError):
                    record_audit('2026-10-13','5230_B_0910.json',x)
            x=self.fixture(); x['trajectory_raw_1m'].insert(1,dict(x['trajectory_raw_1m'][0]))
            with self.assertRaises(AuditError): record_audit('2026-10-13','5230_B_0910.json',x)
            x=self.fixture()
            with self.assertRaises(AuditError): record_audit('2026-10-14','5230_B_0910.json',x)
            with self.assertRaises(AuditError): record_audit('2026-10-13','9999_B_0910.json',x)
        def test_partition(self):
            cases=[(None,None,'NO_D5'),(None,550,CATEGORIES[3]),(550,550,'SAME'),(579,550,'EARLY_1_TO_29'),(580,550,'EARLY_30_PLUS')]
            self.assertEqual({classify(a,b)[0] for a,b,_ in cases},set(CATEGORIES))
            for a,b,c in cases: self.assertEqual(classify(a,b)[0],c)
            with self.assertRaises(AuditError): classify(550,None)
            with self.assertRaises(AuditError): classify(550,551)
        def test_fail_closed_integration(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); day=root/'2026-10-13'; day.mkdir()
                p=day/'5230_B_0910.json'; p.write_text(json.dumps(self.fixture()),encoding='utf-8')
                mf=day/'manifest.json'; m=dict(schema=SCHEMA,date=day.name,files=[p.name],count=1)
                mf.write_text(json.dumps(m),encoding='utf-8')
                r=audit(root); self.assertEqual(r['summary']['eligible'],1)
                x=self.fixture(); x['trajectory_raw_1m']=x['trajectory_raw_1m'][2:]
                p.write_text(json.dumps(x),encoding='utf-8')
                r=audit(root); self.assertEqual(r['summary']['excluded'],1)
                self.assertEqual(r['exclusions'][0]['missing_open'],['09:00','09:01'])
                m['count']=2; mf.write_text(json.dumps(m),encoding='utf-8')
                r=audit(root); self.assertNotIn('summary',r)
                self.assertEqual(r['status'],'BLOCKED_SOURCE_AUDIT')
    outcome=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if outcome.wasSuccessful() else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--root',type=Path)
    parser.add_argument('--out',type=Path,help='New JSON file; existing files never overwritten')
    args=parser.parse_args()
    if args.self_test:
        return self_test()
    if args.root is None or args.out is None:
        parser.error('--root and --out required')
    require(args.root.is_dir(),'MISSING_INPUT_ROOT')
    require(not args.out.resolve().is_relative_to(args.root.resolve()),'OUTPUT_INSIDE_SOURCE_FORBIDDEN')
    result=audit(args.root)
    with args.out.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(result['status'],args.out)
    return 2 if result['blocking_errors'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
