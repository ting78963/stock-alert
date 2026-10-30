# Per-symbol history isolation — implementation contract (2026-10-30)

## Invariants
- Production `main`, Render, existing SQLite and LINE routing stay unchanged until isolated regression tests pass.
- Never fabricate OHLCV or advance `fetch_status.covered_through` without verified source data.
- A symbol with unknown/missing data is **not** eligible for A, B or LINE, but must not prevent verified symbols from running.
- A global provider outage, widespread missing data, corrupt database, or unverified market calendar still fails closed.
- TWSE and TPEx official suspension/trading-interruption notices are separate sources; a 404 or zero volume alone never proves an official suspension.
- Watchlisted symbols are probed each session; resume requires validated catch-up data before eligibility.

## Proposed states
`READY`: verified history through last completed session.
`OFFICIAL_NO_TRADE`: independently verified official non-trading interval with source, date range, and exchange.
`QUARANTINED`: individual data failure with reason, first/last seen, retry schedule, no scan permission.
`RECOVERING`: source resumed; backfill and validate missing sessions before READY.
`GLOBAL_BLOCK`: aggregate/systemic integrity failure; no A launch.

## Isolation boundary
Compute a deterministic eligible symbol set from the SQLite snapshot **before A launches**. Pass a versioned allowlist artifact to A; verify A consumes the exact list before enabling partial launch. Never merely relax `verify_a_history` while A still scans every stock.

## Verification gates
1. Baseline parity: with all symbols READY, new allowlist equals existing universe; A/B output and LINE event identities unchanged.
2. One/multiple OFFICIAL_NO_TRADE: other symbols scan; affected symbols emit no events.
3. One/multiple QUARANTINED: other symbols scan; affected symbols emit no events; alert contains root cause.
4. RECOVERING: official resumption alone is insufficient; historical backfill required.
5. Global API outage, missing schema, missing official calendar, mass stale symbols: fail closed.
6. Repeated restarts, duplicate event protection, no DB schema mutation during read-only preflight.
7. Verify actual worker A → B → LINE with test-only sinks before production rollout.

## Rollout
Implement and test on this feature branch; no merge, no production deployment or database migration until explicit pass/fail evidence exists. Preserve current live commit `a17c852` for immediate rollback.
