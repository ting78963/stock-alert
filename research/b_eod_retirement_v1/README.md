# B EOD retirement v1 — isolated research

Baseline Render production commit: `d2009fc4d13e2fa9e5a88a0eaee72e80f0278106`.
Render worker: `srv-dasvnou0tbcc7399tl90`.
Reference source: `production_worker_v2_shared_ws.py`, production SHA256 `40c2e9970cb06a7c1bc9947f3cd43c87c2469c830634c696bc80add5dcd8e8b2`.

## Objective
Safely retire end-of-day B runners after all final-minute processing and notification handling, without changing A, VCP, new A, P1/ABC recognition, LINE, or F14 dedupe.

## Historical baseline (2026-10-15)
53 B stock folders; 49 no-event stocks had canonical last minute 13:30 and persisted state_through 13:30; four sent event stocks: 2377 P1, 6127 P1, 6108 ABC, 9914 ABC. Historical persistence alone does NOT prove queue drain, REST final-bar completeness, or thread exit.

## Required acceptance gates (fail closed)
1. End-of-session gate must reject new same-day B handoffs atomically, including launches already in progress; next-day lifecycle unaffected.
2. Quiesce WS routing and reconnect reconciliation without losing a pending revision.
3. Drain each FIFO queue and confirm worker completion; no global lock held while waiting for worker or runner lock.
4. Reconcile authoritative completed final bars and evaluate unchanged P1/ABC logic; do not treat persisted 13:30 as independent REST verification.
5. Do not retire if REST fails, queue overflows, worker fails, or unsent LINE event remains; preserve retry and diagnostic visibility.
6. F14 means successful LINE only; EOD no-signal closure needs separate idempotent marker.
7. Verify no new WS subscription or B launch after EOD gate; verify worker threads and registries, not just RSS.
8. Verify no changes to production signal identities, recognition times, or notifications in frozen replay.
9. Test concurrent discovery, WS callback, clock, reconnect, LINE success, queue-full sentinel, and restart boundary.
10. No main-branch merge or Render deployment until all tests pass and user approves.

## Scope
Research branch only. No network calls, no production data writes, no LINE, no deployment.
