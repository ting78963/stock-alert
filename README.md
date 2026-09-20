# stock-alert — Fugle A/B/C production

The legacy limit-up/group/golden/spark/fire/trailing/statistics strategy has been removed.

New production architecture:

`A discovery -> B REST backfill -> original Attack/A2 -> Frozen Early -> A/B/C -> LINE`

Environment:
- FUGLE_API_KEY
- LINE_TOKEN
- GROUP_ID

Health:
- GET /ping
- GET /status

The broad-market A scanner is not enabled until the Fugle account has Snapshot permission. The audited B modules are being installed directly into this repository.
