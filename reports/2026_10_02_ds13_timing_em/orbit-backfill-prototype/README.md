# Seed-preserving orbit backfill prototype

This recorded-corpus replay uses sealed DS13 reference-position orbit/posterior arrays. It tests sparse membership recovery, not a standalone blind or streaming orbit fit.

New membership is restricted to GLRT groups unused by every accepted initial proposal. Groups owned by another initial identity are never reassigned.

| Scan | Recovered / seeded | Dense edges | Retrieved edges | Selected groups | Unallocated fill | Tight contested excluded |
|---|---:|---:|---:|---:|---:|---:|
| A | 11 / 11 | 81444 | 4142 | 1356 | 690 | 147 |
| B | 9 / 11 | 74624 | 3268 | 1076 | 598 | 127 |

Prototype wall time: 0.704 seconds.

Gate: ±2.5 kHz retrieval, posterior ≥0.90, runner-up ≤0.05, |residual| ≤150 Hz, maximum gap 3 seconds, and at least five original seed groups.
