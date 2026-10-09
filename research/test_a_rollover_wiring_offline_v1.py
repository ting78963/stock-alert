#!/usr/bin/env python3
"""Offline A date rollover and worker wiring audit. No production execution."""
import ast,importlib.util
from pathlib import Path
guard=Path("/tmp/a_session_rollover_guard_v1.py")
spec=importlib.util.spec_from_file_location("a_rollover_test",guard)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.assert_a_session_identity("2026-10-12","2026-10-12","2026-10-08")
print("PASS: same-day A may continue")
for today,verified,required in [
    ("2026-10-13","2026-10-12","2026-10-08"),
    ("2026-10-12","2026-10-12","2026-10-12"),
    ("2026-10-12","2026-10-12",""),
]:
    try:m.assert_a_session_identity(today,verified,required)
    except m.ASessionRolloverError:pass
    else:raise AssertionError((today,verified,required))
print("PASS: rollover / future watermark / invalid identity fail closed")
worker=Path("/tmp/a_worker_rollover_stage.py").read_text(encoding="utf-8")
scanner=Path("/tmp/a_scanner_rollover_stage.py").read_text(encoding="utf-8")
ast.parse(worker);ast.parse(scanner)
assert 'a_env["A_VERIFIED_SNAPSHOT_DAY"]=now_tpe().date().isoformat()' in worker
assert 'a_env["A_LAST_COMPLETED_SESSION"]=required_session' in worker
assert 'assert_a_session_identity(dt.date().isoformat(), verified_day,' in scanner
assert 'return 2' in scanner.split('[A SESSION ROLLOVER STOP]')[1][:180]
print("PASS: worker passes both verified identities to A")
print("PASS: A contains rollover check before scan")
print("LIMITATION: static wiring audit; does not launch worker or test restart/recovery timing")
print("HTTP_AND_PRODUCTION_WRITES = NONE")
