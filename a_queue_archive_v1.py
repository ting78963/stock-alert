#!/usr/bin/env python3
"""Read-only-first, lossless daily queue audit archiver. No production logic changes."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path('/var/data/stock-alert/a_queue_shadow_audit')
TZ = ZoneInfo('Asia/Taipei')

def digest(path, zipped=False):
    h = hashlib.sha256()
    opener = gzip.open if zipped else open
    with opener(path, 'rb') as f:
        while True:
            b = f.read(1024 * 1024)
            if not b: break
            h.update(b)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--mode', choices=['audit','compress'], default='audit')
    p.add_argument('--min-age-minutes', type=int, default=60)
    a = p.parse_args()
    if a.min_age_minutes < 1: p.error('min age must be positive')
    now = datetime.now(TZ)
    for src in sorted(a.root.glob('????-??-??/queue_shadow_audit.jsonl')):
        day = src.parent.name
        try: d = datetime.strptime(day,'%Y-%m-%d').date()
        except ValueError: print('SKIP invalid date',src);continue
        if d >= now.date(): print('SKIP today/future',src);continue
        st = src.stat()
        if now.timestamp()-st.st_mtime < a.min_age_minutes*60:
            print('SKIP recently modified',src);continue
        dst = src.with_suffix('.jsonl.gz')
        if dst.exists():
            if digest(src) != digest(dst,True):
                print('FAIL existing archive differs',dst);continue
            print('PASS existing archive verified',day,'original retained');continue
        if a.mode == 'audit':
            print('READY',day, f'{st.st_size/1024**2:.2f} MiB');continue
        print('COMPRESS',day,flush=True)
        tmp = dst.with_name(dst.name + '.part')
        if tmp.exists():
            print('STOP incomplete temporary archive exists; manual review required', tmp)
            continue
        try:
            with src.open('rb') as fi, tmp.open('xb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=6) as fo:
                    while True:
                        b = fi.read(1024*1024)
                        if not b:break
                        fo.write(b)
                raw.flush();os.fsync(raw.fileno())
            end = src.stat()
            if (st.st_size,st.st_mtime_ns,st.st_ino)!=(end.st_size,end.st_mtime_ns,end.st_ino):
                print('FAIL source changed during archive; manual review required',day);continue
            if digest(src)!=digest(tmp,True):
                print('FAIL SHA256 mismatch; original retained',day);continue
            os.replace(tmp, dst)
            print('PASS',day,f'{st.st_size/1024**2:.2f} -> {dst.stat().st_size/1024**2:.2f} MiB','SHA256 matched; original retained')
        except Exception as e:
            print('FAIL',day,type(e).__name__,str(e),'original retained')
    print('DONE; no originals deleted')

if __name__=='__main__':main()
