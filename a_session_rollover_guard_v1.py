# -*- coding: utf-8 -*-
"""Pure A session rollover guard. Fail closed if launch watermark belongs to another day."""
from datetime import date

class ASessionRolloverError(RuntimeError): pass

def assert_a_session_identity(snapshot_day, verified_snapshot_day, required_session):
    try:
        current=date.fromisoformat(str(snapshot_day)[:10])
        verified=date.fromisoformat(str(verified_snapshot_day)[:10])
        required=date.fromisoformat(str(required_session)[:10])
    except (ValueError,TypeError) as exc:
        raise ASessionRolloverError("invalid verified session identity") from exc
    if current != verified:
        raise ASessionRolloverError(
            f"A date rollover: verified_for={verified} current={current}; restart with fresh calendar/DB preflight"
        )
    if required >= current:
        raise ASessionRolloverError("last completed session must precede snapshot")
    return True
