# DS27 causal catalogue and initialization audit

All 15 frozen fast cases retained: 13 passed, 2 snapshot unavailable, 0 failed/error. Evaluation sealed: True. No GPS truth was read; no inference was rerun.

Every recorded nominal, previous and phase-history epoch/collection is checked against the scan cutoff. Bank/TLE bytes are checked against the public snapshot descriptor and their receipts. Available snapshots must use the fixed 25 km box centered at 37.906, -122.545, zero initial offset, no reference position and no candidate whitelist. The broad catalogue prefilter uses a separate 250 km region.

| Case | Status | Candidates | Latest epoch age range (h) | Latest collection age range (h) |
|---|---|---:|---:|---:|
| DS27-0001 | snapshot_unavailable | — | — | — |
| DS27-0002 | pass | 1700 | 7.832–47.575 | 0.526–0.526 |
| DS27-0004 | pass | 1557 | 2.084–47.488 | 0.006–0.006 |
| DS27-0006 | snapshot_unavailable | — | — | — |
| DS27-0008 | pass | 1361 | 6.152–47.950 | 1.096–1.096 |
| DS27-0010 | pass | 1410 | 7.656–47.752 | 0.650–0.650 |
| DS27-0012 | pass | 1467 | 7.161–47.680 | 1.136–1.136 |
| DS27-0014 | pass | 1633 | 4.999–47.392 | 0.964–0.964 |
| DS27-0016 | pass | 1582 | 3.468–47.439 | 0.820–0.820 |
| DS27-0018 | pass | 1530 | 4.972–47.558 | 0.298–0.298 |
| DS27-0020 | pass | 1452 | 6.476–47.951 | 1.802–1.802 |
| DS27-0022 | pass | 1393 | 6.527–47.177 | 1.329–1.329 |
| DS27-0024 | pass | 1402 | 4.811–45.425 | 0.881–2.833 |
| DS27-0026 | pass | 1486 | 6.314–45.704 | 1.311–4.337 |
| DS27-0028 | pass | 1575 | 7.818–47.474 | 0.894–5.840 |

Unavailable cases: DS27-0001 — no_existing_public_GLRT_input (baseline unavailable); DS27-0006 — no public completed snapshot descriptor (baseline failed).

1053 checks performed. Unavailable cases retain their recorded pipeline state in the JSON. Per-case hashes, all check failures, previous-catalogue and phase-history ages are in the JSON. Hash agreement establishes frozen provenance consistency; it does not establish orbit or localization accuracy.

Manifest: `sha256:a0cf50e71336519b649677c91ae39ef2438a14b6e007ce2bc70da2b47211af32`. Audit source: `sha256:d4edc2304f1fa68ca4aada2cfbdc94584bd269aa3f20c8211d9d87e8ba6c0d7a`.
