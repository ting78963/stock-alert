#!/usr/bin/env python3
"""Staging-only guarded launcher for phase1_fugle_daily_builder_v1.py.
No production runner, A/B/P1 or LINE modifications. No automatic scheduling.
"""
import argparse
import datetime as dt
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

TZ = dt.timezone(dt.timedelta(hours=8))
LOCK = Path("/var/data/stock-alert/shared_history_builder.lock")
DEFAULT_BUILDER = Path("/tmp/phase1_fugle_daily_builder_v1.py")
# Conservative weekday window, including preparation and post-close buffer.
BLOCK_START = dt.time(8, 30)
BLOCK_END = dt.time(14, 0)


def in_protected_hours(now):
    return now.weekday() < 5 and BLOCK_START <= now.time() < BLOCK_END


def cgroup_headroom_mib():
    for base in (Path("/sys/fs/cgroup"),):
        try:
            maximum = (base / "memory.max").read_text().strip()
            if maximum == "max":
                return None
            used = int((base / "memory.current").read_text().strip())
            return (int(maximum) - used) / (1024 * 1024)
        except (OSError, ValueError):
            pass
    try:
        # cgroup v1 fallback
        base = Path("/sys/fs/cgroup/memory")
        maximum = int((base / "memory.limit_in_bytes").read_text().strip())
        used = int((base / "memory.usage_in_bytes").read_text().strip())
        if maximum > (1 << 50):
            return None
        return (maximum - used) / (1024 * 1024)
    except (OSError, ValueError):
        return None


def main():
    p = argparse.ArgumentParser(description="Guarded staging-only history downloader")
    p.add_argument("--asof", required=True)
    p.add_argument("--builder", type=Path, default=DEFAULT_BUILDER)
    p.add_argument("--min-headroom-mib", type=int, default=180)
    p.add_argument("--check-seconds", type=int, default=2)
    p.add_argument("--dry-run", action="store_true", help="Validate guards only; no child, no network, no DB writes")
    a = p.parse_args()
    if a.min_headroom_mib < 64 or a.check_seconds < 1:
        p.error("invalid safety parameters")
    try:
        asof = dt.date.fromisoformat(a.asof)
    except ValueError:
        p.error("invalid --asof")
    now = dt.datetime.now(TZ)
    if in_protected_hours(now):
        raise SystemExit("STOP: protected Taiwan weekday 08:30-14:00; production priority")
    if not a.builder.is_file():
        raise SystemExit("STOP: builder missing")
    if asof > now.date() + dt.timedelta(days=1):
        raise SystemExit("STOP: future asof")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("STOP: another guarded download holds lock")
        headroom = cgroup_headroom_mib()
        if headroom is None:
            raise SystemExit("STOP: cgroup memory headroom unavailable; fail closed")
        if headroom < a.min_headroom_mib:
            raise SystemExit(f"STOP: low memory headroom {headroom:.1f} MiB")
        print(f"[GUARD PASS] Taiwan={now.isoformat()} headroom={headroom:.1f} MiB, lock acquired", flush=True)
        if a.dry_run:
            print("[DRY RUN] no downloader launched; no network or DB writes", flush=True)
            return
        child = subprocess.Popen([sys.executable, str(a.builder), "--asof", a.asof, "--limit", "0"])
        try:
            while child.poll() is None:
                time.sleep(a.check_seconds)
                reason = None
                if in_protected_hours(dt.datetime.now(TZ)):
                    reason = "protected hours reached"
                available = cgroup_headroom_mib()
                if available is None or available < a.min_headroom_mib:
                    reason = f"memory headroom unsafe ({available} MiB)"
                if reason:
                    print(f"[GUARD STOP] {reason}; terminating downloader", flush=True)
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    raise SystemExit(3)
            if child.returncode:
                raise SystemExit(child.returncode)
            print("[GUARD COMPLETE] downloader exited successfully", flush=True)
        except KeyboardInterrupt:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            raise SystemExit(130)


if __name__ == "__main__":
    main()
