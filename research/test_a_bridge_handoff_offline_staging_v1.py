#!/usr/bin/env python3
"""Isolated actual handoff_hit / bridge_send / mark_sent contract tests.
All network and persistent writes mocked. Never touches production.
"""
import importlib.util
import sys
import unittest.mock as mock

path = "/tmp/a_f11_offline_staging_test.py"
spec = importlib.util.spec_from_file_location("a_bridge_test", path)
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)

scanner = object.__new__(a.Scanner)
scanner.bridge_url = "https://offline.invalid/bridge"
scanner.state = {"discovered": {}, "volume_armed": {}, "queue_waiting": {}}
day = "2026-10-09"
hit = {"code": "1303", "source": "NO_VCP", "name": "TEST",
       "volRatio": 2.0, "chgPct": 3.0}
a.save_json_atomic = mock.Mock()
a.append_event = mock.Mock()
sent = []
class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return b"ok"

def success(req, timeout=10):
    assert req.full_url == scanner.bridge_url
    assert req.get_method() == "POST"
    sent.append(req.data)
    return Response()

with mock.patch.object(a.urllib.request, "urlopen", side_effect=OSError("offline simulated failure")) as net:
    try:
        scanner.handoff_hit(hit, day)
        raise AssertionError("failed Bridge was accepted")
    except RuntimeError as e:
        assert "Bridge handoff failed" in str(e)
    assert not scanner.already_sent(day, "1303")
    assert a.save_json_atomic.call_count == 0
    assert a.append_event.call_count == 0
    assert net.call_count == 1
print("BRIDGE_FAILURE_NO_DEDUPE = PASS")

with mock.patch.object(a.urllib.request, "urlopen", side_effect=success) as net:
    assert scanner.handoff_hit(hit, day) is True
    assert scanner.already_sent(day, "1303")
    assert a.save_json_atomic.call_count == 1
    assert a.append_event.call_count == 1
    assert net.call_count == 1 and len(sent) == 1
    assert scanner.handoff_hit(hit, day) is False
    assert net.call_count == 1 and len(sent) == 1
    assert a.save_json_atomic.call_count == 1
print("BRIDGE_SUCCESS_THEN_DEDUPE = PASS")
print("DUPLICATE_NO_SECOND_POST = PASS")
print("HTTP_REAL = 0; FILE_WRITES_REAL = 0; LINE_REAL = 0")
print("RESULT = PASS")
