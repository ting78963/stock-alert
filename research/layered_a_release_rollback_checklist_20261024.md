# Layered A release / rollback checklist (2026-10-24)

## Immutable baseline
- Production Worker: srv-dasvnou0tbcc7399tl90 (Render), auto-deploys main.
- Production baseline SHA: 7a92b891bf017b6ca73d90a38648fb8647673795.
- Protected reference branch: backup/pre-layered-a-20261023.
- Candidate: release/layered-a-clean-20261023; PR #17 remains draft.
- Do not merge or change Render configuration without explicit approval.

## Verified
- Candidate isolated scanner test and isolated real B launch_b/dedup/F14 test succeeded in GitHub Actions.
- Legacy and target A state.json, vcp_breakout_track_v2.json and events.jsonl matched SHA-256 after manual sync.
- Persistent disk backup: /var/data/stock-alert/a_migration_backups/20261023_145019/{old_a,new_a}/.
- Render worker start command is python production_worker_v1.py; disk /var/data.

## Preconditions not yet verified
1. Read current Worker environment variable *names and relevant nonsecret path values*; ensure A_STATE_DIR=/var/data/stock-alert/a_scanner_v2 or a matching PRODUCTION_STATE_DIR, and check existing B STATE_ROOT persistence.
2. Read-only confirm disk free space and both state directories; do not copy stale files over newer state.
3. Verify startup migration marker/lock behavior with isolated fixture; production marker absent before launch.
4. Record deployed commit, env settings and service config before any production change.
5. Ensure F14 LINE-completed registry and B event files survive restart; never restore old B state over newer B state.

## Normal release (requires explicit user authorization)
- Snapshot current state and environment settings, then merge approved candidate into main; note both Worker and Web auto-deploy main.
- Enable A_LAYERED_A_ENABLED=1 and set durable A state path only after checking env semantics; Render env edits may restart the Worker.
- Validate Worker startup, A history preflight, A -> B handoff, and first trading session. Do not send test LINE messages.

## Failure / rollback
- Stop or disable new layered A before changing files. Capture a timestamped backup of the *current* A state, B F14 registry and B signal event files; never overwrite with the 2026-10-23 backup blindly.
- Preferred quick fallback, where supported: A_LAYERED_A_ENABLED=0 returns to FLOW selection while retaining candidate state layout. Confirm whether restart/deploy is required and ensure no double A processes.
- Full code fallback: restore baseline SHA from backup/pre-layered-a-20261023 and its original Render settings. Baseline A uses legacy _production_output/fugle_a_scanner_v2; it does NOT automatically read A_STATE_DIR. Before launching old A, explicitly reconcile latest A state from persistent storage into the legacy directory (or prepare a tested old-A compatible state-path patch), preserving current records. Do not assume reverting GitHub alone restores state.
- Preserve F14 completion data to prevent duplicate LINE; verify F14 registry and B authoritative events after restart.
- Check B and A logs and monitor first trading session. If path or state reconciliation is uncertain, keep LINE disabled rather than risk duplicate alerts.

## Release decision
NO-GO until state-path, rollback data reconciliation, and B F14 persistence are verified. CI passing alone does not authorize deployment.
