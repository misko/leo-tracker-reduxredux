# Tail-preserving singleton qualification: equivalent, not faster

The separate v2 implementation preserves original log-domain arithmetic on
rows whose signal probabilities approach underflow. It leaves the failed v1
sources and receipts unchanged. Eight component tests passed, including
conditional residuals at 38.5–39 standard deviations and complete derivatives;
Ruff passed. Source commit: dcf6fa38b.

Real-corpus qualification checked all six original physical starts plus the
stationary training winner in each all/low/high view of DS22-001 and 003:
42 states, 84 objective evaluations, zero fits. Every original winner also
replayed its stored objective. Source, input, original matrix and driver
bindings were checked before and after; no reference/held data were used.

| Maximum absolute difference | 001 | 003 |
| --- | ---: | ---: |
| Objective / likelihood NLL | 7.276e-12 | 7.276e-12 |
| Physical gradient | 1.819e-12 | 1.819e-12 |
| Nuisance gradient | 2.220e-16 | 1.110e-16 |
| Satellite probability | 7.216e-16 | 6.661e-16 |
| Conditional residual Hz | 3.070e-12 | 9.095e-13 |

All fields passed the unchanged absolute1e-8 / relative1e-10 gate, including
clutter probabilities and prediction gradients. Qualification completed in
33.541/27.686 seconds including genuine training reconstruction.

However, alternating old/new evaluations provided no useful measured speedup:

| Original seconds / v2 seconds | All | Low | High |
| --- | ---: | ---: | ---: |
| 001 | 1.017 | 1.031 | 1.012 |
| 003 | 0.963 | 1.012 | 1.039 |

These are aggregate timings over seven states per view under shared host load,
not isolated microbenchmarks. They do not justify a claim of acceleration or
new position fits. No scientific matrix has adopted v2. The likelihood cost
remains measured, but this particular tail-safe positive-density approach does
not resolve it; prioritize the independent half-band/model investigations.

Exact per-state deltas, timings, source snapshots and terminal receipts are in
`local/ds22-singleton-qualification-v2/DS22-{001,003}/`.
