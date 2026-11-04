#!/usr/bin/env python3
"""Guarded Render restart client. No deploy calls. Disabled by default.

Requires an external supervisor to first obtain a trustworthy worker status
snapshot and enforce one-attempt-per-day using durable external state.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

WORKER_ID = "srv-dasvnou0tbcc7399tl90"
URL = f"https://api.render.com/v1/services/{WORKER_ID}/restart"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Explicit opt-in to API request")
    parser.add_argument("--approved", action="store_true", help="Supervisor approved preflight and reserved daily attempt")
    args = parser.parse_args()
    if not (args.execute and args.approved):
        print("DRY RUN: restart API not called")
        return 0
    if os.environ.get("ALLOW_WORKER_RESTART") != "yes":
        print("BLOCKED: ALLOW_WORKER_RESTART not enabled", file=sys.stderr)
        return 2
    token = os.environ.get("RENDER_API_KEY", "").strip()
    if not token:
        print("BLOCKED: RENDER_API_KEY missing", file=sys.stderr)
        return 2
    req = urllib.request.Request(
        URL, method="POST",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status != 200:
                print(f"RESTART ERROR: HTTP {response.status}", file=sys.stderr)
                return 1
            print("RESTART REQUEST ACCEPTED (service health not yet verified)")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"RESTART ERROR: HTTP {exc.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"RESTART UNKNOWN: {type(exc).__name__}; do not blindly retry", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
