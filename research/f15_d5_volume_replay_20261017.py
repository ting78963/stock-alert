#!/usr/bin/env python3
"""F15 D5 v4: offline archive audit and volume-only comparison. No network/import side effects.

Schema checked against f15_trajectory_store.py / f15_eod_signal_report.py.
Minute M completion at M+1 follows B completed_cutoff; this is a MODEL,
not evidence of historical arrival. No actual handoff/availability conclusions.
Source rows are never changed. A separate hypothetical no-new-trades grid may
carry cumulative volume across unknown gaps. Explicit volume=0 rows are observed zero volume;
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

def event_seconds(value):
    """HH:MM or HH:MM:SS, same-day clock; never discard nonzero seconds.

    Unlike bar labels, discovery can occur after the trading session.
    HH:MM is interpreted as :00, matching B nt(); no subsecond inference.
    """
    require(isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}(:\d{2})?', value),
            'INVALID_EVENT_TIME: ' + repr(value))
    parts = list(map(int, value.split(':')))
    h, m = parts[:2]; second = parts[2] if len(parts) == 3 else 0
    require(0 <= h < 24 and 0 <= m < 60 and 0 <= second < 60, 'EVENT_TIME_OUTSIDE_DAY')
    return h*3600 + m*60 + second

def event_fmt(value):
    return f'{value//3600:02d}:{value//60%60:02d}:{value%60:02d}'


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
    rec = tm(i.get('recognition_time')); rec_seconds = rec*60
    disc = event_seconds(a.get('discovered_at'))
    require(i.get('date') == day and filename == f'{sid}_{cls}_{fmt(rec).replace(":", "")}.json',
            'IDENTITY_DATE_OR_FILENAME')
    require(e.get('schema') == ('b_signal_event_v2' if cls == 'P1' else 'b_signal_event_v1'),
            'EVENT_SCHEMA')
    require(e.get('date') == day and str(e.get('stock_id','')).zfill(4) == sid
            and e.get('signal_class') == cls and tm(e.get('recognition_time')) == rec,
            'EVENT_IDENTITY_MISMATCH')
    require(e.get('source') == 'Fugle' and e.get('line_sent') is True,
            'EVENT_SOURCE_OR_DELIVERY_UNVERIFIED')
    require(event_seconds(e.get('discovered_at')) == disc, 'DISCOVERY_MISMATCH')
    live = event_seconds(e.get('live_known_time'))
    feed = event_seconds(e.get('signal_emitted_at_feed_through'))
    require(live == max(rec_seconds,disc), 'LIVE_KNOWN_MISMATCH')
    # Feed-through is a data cursor, not emission wall clock: it may precede discovery.
    require(feed >= rec_seconds, 'FEED_THROUGH_BEFORE_RECOGNITION')
    require(type(e.get('late_discovery')) is bool and e['late_discovery'] == (disc > rec_seconds)
            and type(a.get('late_discovery')) is bool
            and a['late_discovery'] == e['late_discovery'], 'LATE_DISCOVERY_MISMATCH')
    exact_delay = max(0,disc-rec_seconds)
    # f15.secs() calls normt()[:5]. Validate this legacy field against its
    # actual producer; NEVER use it for event ordering or exact delay reporting.
    legacy_delay = exact_delay - disc % 60 if disc > rec_seconds else 0
    archived_delay = a.get('delay_seconds')
    require(type(archived_delay) in (int,float) and math.isfinite(archived_delay)
            and archived_delay == legacy_delay, 'ARCHIVED_GENERATOR_DELAY_MISMATCH')
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
    return dict(identity=i, recognition_label=fmt(rec), discovered_at=event_fmt(disc),
                event_time_raw={k:e.get(k) for k in ('discovered_at','live_known_time','signal_emitted_at_feed_through')},
                event_live_known_time=event_fmt(live),
                signal_emitted_at_feed_through=event_fmt(feed),
                delay_seconds_exact=exact_delay,
                archived_delay_seconds=archived_delay,
                archived_delay_policy='F15_GENERATOR_TRUNCATES_SECONDS_NOT_EXACT_DELAY',
                archived_delay_difference_seconds=exact_delay-archived_delay,
                feed_through_semantics='DATA_CURSOR_NOT_EMISSION_WALL_CLOCK',
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

def assumption_compare(record):
    """Independent scenario, NOT proof of zero trades or live availability.

    At label T use observed cumulative through T, carrying only earlier values.
    At decision clock T the completion model uses through T-1, never bar T.
    Initial cumulative=0 before the first observed bar is also an assumption.
    Every clock minute is evaluated, even when a threshold falls without a bar.
    """
    cutoff=tm(record['recognition_label'])
    observed=dict(record['bars'])
    cumulative=0.0; previous=0.0; grid=[]; timeline=[]
    for t in range(540,cutoff+1):
        if t in observed:
            cumulative=observed[t]
        grid.append((t,cumulative))
        timeline.append(dict(minute_label=fmt(t),observed_bar=t in observed,
            volume_status='OBSERVED' if t in observed else 'ASSUMED_NO_NEW_TRADES_UNVERIFIED',
            label_model_cumulative=cumulative,
            completed_model_available_through=fmt(t-1) if t > 540 else None,
            completed_model_cumulative=previous,
            thresholds={k:next((v for start,v in reversed(rule) if t >= start),None)
                        for k,rule in RULES.items()}))
        previous=cumulative
    # Reuse v3 comparison math on a fresh grid; raw records remain untouched.
    comparison=compare(dict(bars=grid,recognition_label=record['recognition_label']))
    return dict(**comparison, timeline=timeline,
        assumption='UNKNOWN_ABSENT_MINUTES_HAVE_NO_NEW_TRADES',
        initial_cumulative_policy='ASSUME_ZERO_BEFORE_FIRST_OBSERVED_BAR',
        missing_minutes_proven_zero=False,
        has_unknown_missing_minutes=bool(record['unknown_missing_minutes']),
        uncertainty='HYPOTHETICAL_VOLUME_ONLY_NOT_HANDOFF_API_AVAILABILITY_OR_TRADE_SIGNAL')


def model_summary(rows, completed=False):
    category_key='completed_bar_model_category' if completed else 'category'
    delta_key='completed_bar_model_advance_minutes' if completed else 'advance_label_minutes'
    categories=tuple('D5_ONLY_BY_RECOGNITION_CLOCK_MODEL' if completed and k ==
                     'D5_ONLY_BY_RECOGNITION_LABEL' else k for k in CATEGORIES)
    counts=Counter(r[category_key] for r in rows)
    require(set(counts) <= set(categories) and sum(counts.values()) == len(rows),
            'MODEL_CATEGORY_PARTITION_FAILURE')
    deltas=[r[delta_key] for r in rows if r[delta_key] is not None]
    return dict(n=len(rows),counts={k:counts[k] for k in categories},paired_n=len(deltas),
                paired_median_advance_minutes_including_same=statistics.median(deltas) if deltas else None)


def load(path):
    data=path.read_bytes()
    return json.loads(data.decode('utf-8')), hashlib.sha256(data).hexdigest()

def audit(root):
    result=dict(version=4, scope='ARCHIVED_F15_DELIVERED_SIGNALS_VOLUME_ONLY',
                source_status='ARCHIVE_INTERNAL_CONSISTENCY_ONLY',
                rule_spec_status='IMPLEMENTED_SCHEDULE_ONLY_NO_INDEPENDENT_D5_SPEC',
                independent_source_completeness='UNVERIFIED_NO_RAW_API_OR_EXTERNAL_EVENT_INVENTORY',
                actual_availability_conclusion='BLOCKED_NO_ARRIVAL_OR_REVISION_PROVENANCE',
                handoff_conclusion='BLOCKED_NOT_AN_A_REPLAY',
                trading_signal_conclusion='BLOCKED_RESEARCH_VOLUME_ONLY',
                time_policy='LABEL <= recognition; completion MODEL M+1 <= recognition clock; thresholds at decision clock',
                event_time_policy='Same-day HH:MM[:SS], compared as integer seconds; HH:MM means :00 per B nt()',
                archived_delay_policy='Validate legacy F15 normt/seconds field separately; exact delay recomputed from event seconds',
                event_semantics_limit='live_known_time=max(discovery, recognition) per B producer, NOT arrival or emission clock; feed-through is data cursor',
                strict_v3_policy='eligible/exclusions/summary retain unchanged v3 complete-sample semantics',
                missing_no_new_trades_scenario=dict(
                    status='PENDING_SOURCE_AUDIT', eligible=[], exclusions=[],
                    policy='Independent hypothetical scenario; gaps are NOT proven zero; initial cumulative assumed zero',
                    uncertainty='NOT_ACTUAL_HANDOFF_API_AVAILABILITY_OR_TRADING_SIGNAL'),
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
                scenario=result['missing_no_new_trades_scenario']
                if r['identity']['stock_id'] == '4906':
                    scenario['exclusions'].append(dict(**entry,reasons=['POLICY_EXCLUDE_4906']))
                else:
                    scenario['eligible'].append(dict(**entry, **assumption_compare(r)))
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
                result['missing_no_new_trades_scenario']['exclusions'].append(dict(entry))
            result['files'].append(entry)
    # No cohort statistics at all if source membership/identity validation failed.
    if result['blocking_errors']:
        result['status']='BLOCKED_SOURCE_AUDIT'; result['eligible']=[]
        scenario=result['missing_no_new_trades_scenario']
        scenario['status']='BLOCKED_SOURCE_AUDIT'; scenario['eligible']=[]
    else:
        result['status']=('AUDITED_SUBSET_LABEL_COMPARISON_ONLY' if result['eligible']
                          else 'NO_ELIGIBLE_SIGNALS_NO_COMPARISON')
        counts=Counter(r['category'] for r in result['eligible'])
        deltas=[r['advance_label_minutes'] for r in result['eligible'] if r['advance_label_minutes'] is not None]
        result['summary']=dict(counts={k:counts[k] for k in CATEGORIES},
            eligible=len(result['eligible']),excluded=len(result['exclusions']),
            paired_n=len(deltas), paired_median_label_advance_including_same=statistics.median(deltas) if deltas else None)
        require(sum(counts.values()) == len(result['eligible']), 'CATEGORY_PARTITION_FAILURE')
        result['strict_v3_completed_bar_model_summary']=model_summary(result['eligible'],True)
        scenario=result['missing_no_new_trades_scenario']
        scenario['status']=('HYPOTHETICAL_COMPARISON_ONLY' if scenario['eligible'] else 'NO_ELIGIBLE_SIGNALS_NO_COMPARISON')
        scenario['label_model_summary']=model_summary(scenario['eligible'])
        scenario['completed_bar_model_summary']=model_summary(scenario['eligible'],True)
        scenario['unknown_missing_minutes_total']=sum(len(r['unknown_missing_minutes']) for r in scenario['eligible'])
        scenario['signals_with_unknown_missing_minutes']=sum(r['has_unknown_missing_minutes'] for r in scenario['eligible'])
        scenario['missing_minutes_by_location']={
            key:sum(len(r[key]) for r in scenario['eligible'])
            for key in ('missing_open','missing_internal','missing_tail')}
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
        def seconds_fixture(self, discovered, live=None):
            x=self.fixture(); e=x['production_event_snapshot']; a=x['causal_anchor']
            seconds=event_seconds(discovered); rec=tm(x['identity']['recognition_time'])*60
            e['discovered_at']=a['discovered_at']=discovered
            e['live_known_time']=live or event_fmt(max(seconds,rec))
            e['late_discovery']=a['late_discovery']=seconds > rec
            a['delay_seconds']=max(0,seconds-rec-seconds%60)
            return x
        def test_event_parser_seconds(self):
            self.assertEqual(event_seconds('13:12:07'),47527)
            self.assertEqual(event_seconds('09:10'),33000)
            self.assertEqual(event_fmt(event_seconds('13:31:59')),'13:31:59')
            for bad in ('13:12:60','24:00:00','09:60:00','9:10:07','09:10:07junk',None):
                with self.assertRaises(AuditError): event_seconds(bad)
            with self.assertRaises(AuditError): tm('13:12:07')
        def test_nonzero_seconds_delay(self):
            for discovery,expected,archived in [('09:10:07',7,0),('09:11:01',61,60),
                                                ('13:12:07',14527,14520),('09:09:59',0,0),
                                                ('09:10:00',0,0)]:
                r=record_audit('2026-10-13','5230_B_0910.json',self.seconds_fixture(discovery))
                self.assertEqual(r['delay_seconds_exact'],expected)
                self.assertEqual(r['archived_delay_seconds'],archived)
                self.assertEqual(r['discovered_at'],discovery)
            # Early discovery is valid; live-known stays at recognition label.
            r=record_audit('2026-10-13','5230_B_0910.json',self.seconds_fixture('09:09:59'))
            self.assertEqual(r['event_live_known_time'],'09:10:00')
        def test_seconds_ordering_and_legacy_delay(self):
            x=self.seconds_fixture('09:10:07','09:10:00')
            with self.assertRaisesRegex(AuditError,'LIVE_KNOWN_MISMATCH'):
                record_audit('2026-10-13','5230_B_0910.json',x)
            x=self.seconds_fixture('09:10:07'); x['causal_anchor']['discovered_at']='09:10:08'
            with self.assertRaisesRegex(AuditError,'DISCOVERY_MISMATCH'):
                record_audit('2026-10-13','5230_B_0910.json',x)
            x=self.seconds_fixture('09:10:07'); x['production_event_snapshot']['signal_emitted_at_feed_through']='09:09:59'
            with self.assertRaisesRegex(AuditError,'FEED_THROUGH_BEFORE_RECOGNITION'):
                record_audit('2026-10-13','5230_B_0910.json',x)
            x=self.seconds_fixture('09:10:07'); x['causal_anchor']['delay_seconds']=7
            with self.assertRaisesRegex(AuditError,'ARCHIVED_GENERATOR_DELAY_MISMATCH'):
                record_audit('2026-10-13','5230_B_0910.json',x)
            # Cursor is not an emission timestamp; earlier than discovery is legal.
            x=self.seconds_fixture('13:12:07'); x['production_event_snapshot']['signal_emitted_at_feed_through']='09:10:01'
            self.assertEqual(record_audit('2026-10-13','5230_B_0910.json',x)['delay_seconds_exact'],14527)
            x=self.seconds_fixture('09:10:07'); x['identity']['recognition_time']='09:10:07'
            with self.assertRaises(AuditError): record_audit('2026-10-13','5230_B_0910.json',x)
        def test_realistic_seconds_integration(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); day=root/'2026-10-13'; day.mkdir()
                p=day/'5230_B_0910.json'
                p.write_text(json.dumps(self.seconds_fixture('13:12:07')),encoding='utf-8')
                (day/'manifest.json').write_text(json.dumps(dict(schema=SCHEMA,date=day.name,files=[p.name],count=1)),encoding='utf-8')
                r=audit(root)
                self.assertEqual(r['version'],4)
                self.assertEqual(r['blocking_errors'],[])
                self.assertEqual(r['summary']['eligible'],1)
                self.assertEqual(r['eligible'][0]['delay_seconds_exact'],14527)
        def hypothetical(self,bars,cutoff):
            present={t for t,_ in bars}
            return assumption_compare(dict(bars=bars,recognition_label=fmt(cutoff),
                unknown_missing_minutes=[fmt(t) for t in range(540,cutoff+1) if t not in present]))
        def test_gap_threshold_drops_every_minute(self):
            for boundary,volume in [(550,1700),(560,1400),(570,1100),(580,1000)]:
                r=self.hypothetical([(540,volume)],boundary)
                self.assertEqual(r['label_hits']['D5'],fmt(boundary))
                self.assertEqual(r['completed_bar_model_hits']['D5'],fmt(boundary))
                self.assertEqual(len(r['timeline']),boundary-540+1)
                self.assertFalse(r['timeline'][-1]['observed_bar'])
            r=self.hypothetical([(540,2000)],550)
            self.assertEqual(r['label_hits']['OLD'],'09:10')
            self.assertEqual(r['completed_bar_model_hits']['OLD'],'09:10')
        def test_interval_trading_and_consecutive_gaps(self):
            # Synthetic interval trading pattern; no assertion about actual disposition status.
            r=self.hypothetical([(540,500),(545,1000),(550,1500),(555,2000)],560)
            self.assertEqual(r['label_hits']['D5'],'09:15')
            self.assertEqual(r['completed_bar_model_hits']['D5'],'09:16')
            self.assertEqual(r['label_hits']['OLD'],'09:15')
            self.assertEqual([z['label_model_cumulative'] for z in r['timeline'][1:5]],[500]*4)
            self.assertFalse(r['missing_minutes_proven_zero'])
        def test_assumption_completion_no_future_volume(self):
            r=self.hypothetical([(550,1700),(551,9000)],550)
            self.assertEqual(r['label_hits']['D5'],'09:10')
            self.assertIsNone(r['completed_bar_model_hits']['D5'])
            self.assertEqual(r['timeline'][-1]['completed_model_cumulative'],0)
            r=self.hypothetical([(549,1700)],550)
            self.assertEqual(r['completed_bar_model_hits']['D5'],'09:10')
            self.assertEqual(r['timeline'][-1]['completed_model_available_through'],'09:09')
        def test_open_and_pre_recognition_gaps(self):
            r=self.hypothetical([(542,1800)],550)
            self.assertEqual(r['timeline'][0]['label_model_cumulative'],0)
            self.assertEqual(r['timeline'][1]['label_model_cumulative'],0)
            self.assertEqual(r['timeline'][-1]['label_model_cumulative'],1800)
            self.assertEqual(r['label_hits']['D5'],'09:10')
            self.assertEqual(r['completed_bar_model_hits']['D5'],'09:10')
            self.assertEqual(self.hypothetical([(550,1700)],549)['label_hits']['D5'],None)
        def test_dense_scenario_matches_v3_both_models(self):
            for volume in (0,999,1000,1400,1700,2000,4000):
                bars=[(t,volume) for t in range(540,581)]
                record=dict(bars=bars,recognition_label='09:40',unknown_missing_minutes=[])
                strict=compare(record); scenario=assumption_compare(record)
                for k,v in strict.items(): self.assertEqual(scenario[k],v)
                for completed in (False,True):
                    summary=model_summary([scenario],completed)
                    self.assertEqual(sum(summary['counts'].values()),1)
                self.assertFalse(scenario['has_unknown_missing_minutes'])
        def test_scenario_separation_hash_and_fail_closed(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); day=root/'2026-10-13'; day.mkdir()
                x=self.fixture(); x['trajectory_raw_1m']=[dict(minute='09:02',volume=1800,cum_volume=1800)]
                p=day/'5230_B_0910.json'; p.write_text(json.dumps(x),encoding='utf-8')
                original=p.read_bytes(); digest=hashlib.sha256(original).hexdigest()
                mf=day/'manifest.json'; m=dict(schema=SCHEMA,date=day.name,files=[p.name],count=1)
                mf.write_text(json.dumps(m),encoding='utf-8')
                r=audit(root); scenario=r['missing_no_new_trades_scenario']
                self.assertEqual(r['summary']['eligible'],0)
                self.assertEqual(r['summary']['excluded'],1)
                self.assertEqual(scenario['label_model_summary']['n'],1)
                self.assertEqual(scenario['eligible'][0]['sha256'],digest)
                self.assertEqual(scenario['eligible'][0]['missing_open'],['09:00','09:01'])
                self.assertEqual(scenario['eligible'][0]['label_hits']['D5'],'09:10')
                self.assertEqual(p.read_bytes(),original)
                m['count']=2; mf.write_text(json.dumps(m),encoding='utf-8')
                blocked=audit(root)['missing_no_new_trades_scenario']
                self.assertEqual(blocked['status'],'BLOCKED_SOURCE_AUDIT')
                self.assertEqual(blocked['eligible'],[])
                self.assertNotIn('label_model_summary',blocked)
        def test_scenario_excludes_4906_and_preserves_complete(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); day=root/'2026-10-13'; day.mkdir(); names=[]
                expected=compare(record_audit(day.name,'5230_B_0910.json',self.fixture()))
                for sid in ('5230','4906'):
                    x=self.fixture(); x['identity']['stock_id']=sid; x['production_event_snapshot']['stock_id']=sid
                    p=day/f'{sid}_B_0910.json'; p.write_text(json.dumps(x),encoding='utf-8'); names.append(p.name)
                (day/'manifest.json').write_text(json.dumps(dict(schema=SCHEMA,date=day.name,files=names,count=2)),encoding='utf-8')
                r=audit(root); scenario=r['missing_no_new_trades_scenario']
                self.assertEqual(r['summary']['eligible'],1)
                self.assertEqual(scenario['label_model_summary']['n'],1)
                self.assertEqual(scenario['exclusions'][0]['reasons'],['POLICY_EXCLUDE_4906'])
                for k,v in expected.items(): self.assertEqual(r['eligible'][0][k],v)
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
