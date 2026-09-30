# DS11 complete recordings after DS10

DS11 is minted with **87 recordings**, **192676 visits**, and **23124.96 seconds (6.4236 hours) of valid IQ per receiver**. Six of 93 candidates were excluded for incomplete analysis. Raw IQ remains in its source store; referenced compressed volume is 975079355828 bytes, approximately 0.975 TB.

| Property | Frozen value |
|---|---|
| Lower boundary, last admitted DS10 capture end | 2026-09-29 12:55:05.057462 UTC |
| Request cutoff | 2026-09-30 01:40:39 UTC |
| First admitted capture start | 2026-09-29 12:57:08.132675 UTC |
| Last admitted capture end | 2026-09-30 01:10:41.428265 UTC |
| 2.5 / 5 / 7.5 / 10 MS/s recordings | 15 / 21 / 14 / 37 |
| Chronological complete groups of eight / remainder | 10 / 7 |

The authoritative membership is [local/manifest.json](local/manifest.json). [local/candidate-index.json](local/candidate-index.json) freezes all candidates, and [local/evaluation-units.json](local/evaluation-units.json) gives singles, chronological groups, rate strata and the full set. The latter are evaluation views, not training/test splits. Membership will not expand as excluded recordings finish analysis.

Admission reuses DS10's published/finalized/UTC-qualified capture, transport integrity, complete visits, restored state, complete 120 ms-stride GLRT and bound complete tracking/trajectory/TLE requirements. Tracking creation must precede the fixed cutoff. Full read-only API responses and exclusion reasons are retained. Readiness is observed during inventory, not as an atomic database snapshot. No new analysis or RF collection is launched to make a capture eligible.

Sealing verifies metadata digests, parent boundary, uniqueness, counts, analysis bindings and evaluation units. DS11 is disjoint from DS7, DS8, DS9 and DS10 by session ID and raw manifest digest. Seventeen DS11-owned admission tests pass, including cutoff, provenance, incomplete analysis and seal tamper rejection. [mint.py](mint.py) supports read-only collection and offline verification; [local/SHA256SUMS](local/SHA256SUMS) binds membership and analysis evidence.

Pose companions were not collected for this snapshot. Pose continuity and reference uncertainty are not inferred from dataset membership. IQ is referenced in place rather than copied, decompressed or rehashed; this snapshot is not a backup or a retention hold.

The [32-single-scan benchmark protocol](../2026_09_30_ds11_single10/PROTOCOL.md) selects chronological ranks 1, 3, 6, 9, 12, 14, 17, 20, 23, 25, 28, 31, 34, 37, 39, 42, 45, 48, 50, 53, 56, 59, 62, 64, 67, 70, 73, 75, 78, 81, 84 and 87. This selection was frozen before model evaluation and includes 4 / 9 / 5 / 14 scans at 2.5 / 5 / 7.5 / 10 MS/s.

Artifacts are local; no remote publication or production change occurred.

The [completed 32-scan, ten-method benchmark](../2026_09_30_ds11_single10/README.md) contains all 320 qualified evaluations, aggregate metrics, the full per-scan table and the DS10 comparison.
