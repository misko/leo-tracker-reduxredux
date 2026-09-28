# DS7 chronological group panels

This report collates the eleven sealed, disjoint eight-capture panels. It does not compute a pooled coordinate or rerun any fit. Errors use the evaluator’s great-circle horizontal metric with mean Earth radius 6,371,008.8 m.

| Panel | Captures | Joint | Equal | Inverse RMS² | Lowest RMS 75% | Span (s) |
|---|---:|---:|---:|---:|---:|---:|
| group8-01 | 001–008 | 2541.48 m | 1930.07 m | 2152.44 m | 2532.71 m | 3272.672 |
| group8-02 | 009–016 | 887.79 m | 628.67 m | 601.07 m | 836.50 m | 3268.713 |
| group8-03 | 017–024 | 687.64 m | 984.89 m | 602.57 m | 507.90 m | 3269.817 |
| group8-04 | 025–032 | 783.48 m | 224.21 m | 885.36 m | 1031.55 m | 3269.747 |
| group8-05 | 033–040 | 1086.01 m | 776.36 m | 944.46 m | 854.40 m | 3270.930 |
| group8-06 | 041–048 | 1562.55 m | 1667.45 m | 1634.11 m | 1503.75 m | 3268.890 |
| group8-07 | 049–056 | 3602.97 m | 4292.71 m | 4567.12 m | 5672.24 m | 3270.786 |
| group8-08 | 057–064 | 1545.67 m | abstained (Unqualified upstream estimate) | abstained (Unqualified upstream estimate) | abstained (Unqualified upstream estimate) | 3267.714 |
| group8-09 | 065–072 | 1429.43 m | 1258.81 m | 1206.90 m | 1331.79 m | 3270.158 |
| group8-10 | 073–080 | 2104.71 m | 2908.51 m | 3091.75 m | 2618.20 m | 3269.129 |
| group8-11 | 081–088 | 1322.09 m | 443.02 m | 602.41 m | 446.91 m | 3272.609 |

All eleven scientific joint panels qualified, converged, and were interior. Ten of eleven panels qualified for each control. All three group8-08 controls abstained because an upstream estimate was unqualified; they were not assigned errors. No panel score has a boundary hit.

Across qualified panels:
- **scientific joint:** 11/11 qualified, median 1429.43 m, range 687.64–3602.97 m, 3 below 1 km, 0 abstained.
- **equal:** 10/11 qualified, median 1121.85 m, range 224.21–4292.71 m, 5 below 1 km, 1 abstained.
- **inverse rms2:** 10/11 qualified, median 1075.68 m, range 601.07–4567.12 m, 5 below 1 km, 1 abstained.
- **lowest rms75:** 10/11 qualified, median 1181.67 m, range 446.91–5672.24 m, 4 below 1 km, 1 abstained.

## Preserved failure and qualification history

The original Wave2 `prefix4-01` loader attempt failed closed (`ValueError: Adapter exited 1`) and remains sealed at `reports/2026_09_27_ds7_wave2/solver/prefix4-panel-v1/results.json` (SHA-256 `a6b1857c79a635c9b4b68183fe3752f0ae21b09a2964195b51c8e6424e8b1dc1`). The repaired loader later produced the qualified group8-01 result without changing membership or the scientific selection rule. This historical failure is not counted as a group-panel score.

Group8-08 controls remain explicit abstentions because one required upstream single estimate was unqualified at the frozen position boundary. The group8-08 scientific joint fit qualified because it operates directly on frozen observations and candidate banks rather than aggregating the unqualified single estimate.

## Source binding

Every method entry in `group-panels-v1.json` records its source score path, file SHA-256, embedded score content digest, and run-seal digest. The Wave9 closeout that seals group10 has SHA-256 `5d8caa4398ebcfb69b6a9a4828e327211feb913641bab5da56e6d55d8e319856`.
