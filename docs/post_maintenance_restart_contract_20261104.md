# Post-maintenance safe restart — implementation contract

Status: DESIGN ONLY. Do not deploy a scheduler or change production Worker until tests and credentials are verified.

## Trigger
- Asia/Taipei local date; scheduled trading days only.
- Start the two-hour wait from the durable daily-maintenance LINE-success timestamp, **not** from a process-local timer or the user's phone receipt.
- The existing daily-maintenance state currently stores only a boolean; extend it with an ISO 8601 accepted-at timestamp before enabling scheduling.
- A separate supervisor checks periodically. It must not run in stock-alert-trend-worker itself.

## Preflight (read-only, bounded)
1. DAILY_K and F10 marked completed for this date in persistent state.
2. LINE daily-maintenance report accepted by API; its successful status persists across redeploys.
3. Verify F15 required end-of-day work has completed for the date. Do not mistake the DAILY_K/F10 LINE report for F15 completion.
4. No live A scan/B runner or pending handoff; outside market session.
5. Read-only DB integrity/readability checks and disk headroom. Avoid rescanning 1,447 symbols.
6. Record current memory, deployment ID, commit, and timestamp.
7. A single durable daily restart claim prevents repeated attempts. Never overwrite an unknown/failed state silently.

## Restart
- The external supervisor requests a same-commit Render deploy **once** after preflight passes.
- No data deletion, no code changes, no cache clearing.
- Verify new deployment status and new instance health with a deadline; do not treat the API request being accepted as successful restart.
- No automatic repeated redeploy on failure.

## LINE outcomes
- Success: new deploy live, pre/post memory, times, commit and all checks.
- Failure: failed phase, Render deployment status, observed error, safe next action.
- Skipped: failed preflight and reason; original Worker remains running.
- Stable per-day/per-outcome LINE retry keys; avoid duplicate messages across supervisor retries.
- Report failures must be visible in supervisor logs and retried with bounded policy.

## Operational constraints
- The Render Cron service does not share the Worker's /var/data disk. It needs a secure, read-only way to obtain durable maintenance state, or a dedicated shared store. Do not assume local filesystem access.
- The Render API token must be scoped and stored as a secret; never commit it to GitHub or echo it to logs.
- LINE API accepted != phone delivery confirmed.
- A new Render Cron job may incur costs. Confirm plan/cost before creating it.
- Ensure 11/04 legacy LINE success is not treated as new persistent-state success.
- Test dry-run, no-op, failure, timeout, already-restarted and next-day rollover cases before enabling.
