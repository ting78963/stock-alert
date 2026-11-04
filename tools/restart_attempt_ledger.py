#!/usr/bin/env python3
"""Persist a daily restart reservation; does not invoke Render."""
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TPE = ZoneInfo('Asia/Taipei')

def reserve(directory, now=None):
    now = now or dt.datetime.now(TPE)
    if now.tzinfo is None:
        raise ValueError('timezone required')
    day = now.astimezone(TPE).date().isoformat()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (day + '.json')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'date': day, 'attempt_reserved_at': now.isoformat()}, f)
        f.flush()
        os.fsync(f.fileno())
    return True
