# Partial recovery receipt audit

Snapshot time: 2026-10-09T19:08:25Z. This is not a refreshed full-cohort report.
Protocol SHA256: `24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227`.
All 5,573 frozen source hashes match. At this snapshot 15 candidate receipts are
complete, none terminal failed, four contain recovered-region triggers and none
changes either operational endpoint vector from its reconstructed baseline.
Workers remain live; counts can change. No reference errors were read.

Recovered triggers occur in DS17-002, DS18-004 and newer development members
002/003. Their calibration recoveries qualify. Among their 24 regional finals,
23 qualify and one fails the unchanged independent KKT gate: newer002 fitted-c
own-continuation has KKT 0.001532770535 against 0.001, stop reason
`nonstationary-solver-status-0`, 12 evaluations and 0.08455 seconds.
This is numerical qualification failure, not time/evaluation-budget exhaustion.

For that same region, fitted association qualifies at KKT 0.0008334275602,
651 evaluations/4.0682 seconds, objective 38327.41441457178. Own-continuation
has objective 38327.41441514739, only 5.7561e-7 higher. Its position differs by
approximately 1.0e-8 km, and other displayed coefficients agree to floating-point
precision. Both report a boundary. The saved endpoints support active-bound
qualification sensitivity on an effectively identical solution, rather than a
distinct physical minimum. Exact active normals were not recomputed, so the
precise sensitivity mechanism remains conditional.

The separate zero-timing fitted start qualifies at KKT 0.0003424105744 but has
objective 44419.78186132403 and a distinct position. Qualified association is
retained and ordinary regions remain preserved. Both final operational endpoint
vectors for newer002 equal their baseline exactly. This isolated rejected start
does not justify per-recording tuning or an accuracy claim; preserve it in raw
qualification/failure reporting and wait for full-cohort evidence.

This audit used saved receipts and hashes only: no new fit, objective evaluation,
reference-guided decision, frozen-file change or published snapshot refresh.
