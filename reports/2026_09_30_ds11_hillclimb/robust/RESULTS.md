# Robust IID Student-t screen

The frozen `wave1_vectorized` screen completed all 32 attempts: four likelihood
variants on DS11 indices 0, 4, 8, 12, 16, 20, 24, and 28. All 32 processes
exited zero and all 32 selected fits passed the optimizer, boundary, gradient,
and finite-difference audit gates. There were no scientific or numerical
failures. Total process wall time was 1,247.1 seconds.

| Variant | Qualified | Paired wins | Median error (m) | P90 (m) | Max (m) | Sub-km | Common IID held gain | Screen gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| df4, scale 50 Hz | 8/8 | 0 | 3,659.84 | 6,398.38 | 6,462.99 | 0 | -111.42 | fail |
| df4, scale 200 Hz | 8/8 | 6 | 3,095.84 | 5,667.78 | 6,015.28 | 3 | -14.33 | fail |
| df2, scale 100 Hz | 8/8 | 0 | 3,565.31 | 6,211.96 | 6,443.85 | 1 | -30.53 | fail |
| df8, scale 100 Hz | 8/8 | 6 | 3,088.71 | 6,036.93 | 6,173.47 | 3 | +24.46 | fail |
| Matched original IID | 8/8 | — | 3,108.16 | 6,046.04 | — | — | — | — |

The df8 and scale-200 arms each won six paired comparisons, but reduced median
error by only 0.63% and 0.40%, respectively. The protocol requires at least a
10% median reduction, so no robust-likelihood variant advances to the
within-DS11 replication panel. The common-IID held score is diagnostic only and
does not change that decision.

The final model source SHA-256 is
`ace46eece45ae6ce6e9caa28ea8449101486d25a5891ba8274d5af861750f2ee`.
Every `wave1_vectorized` result records that hash. Six focused tests cover
normalized densities and fixed variant parameters, frozen df4/scale-100
profile parity, profiled envelope gradients and held-row isolation,
stationarity and independent dense multimode selection on a synthetic fixture,
multi-document timing-gradient assembly, and scalar/vectorized bracketing
equivalence. The maximum start-level derivative audit discrepancy was
`3.59e-6`; the maximum selected-fit gradient was `4.44e-4`.

An initial pre-vectorization scale-50/index-0 fit completed in 70.1 seconds.
The exact source is retained as
`model.pre_vectorized.66a9ee0e086aa567.py`; its SHA-256 is
`66a9ee0e086aa5673fe1ee53ec4c017f714a54a42e63090bbb064118d23b8283`.
The next attempt, index 4, was interrupted before producing a result and has an
explicit engineering-only receipt. Vectorizing only the stationary-node
gradient reduced the repeated index-0 wall time to 43.8 seconds and reproduced
its selected score and coordinates exactly. The new stage keeps this throughput
amendment separate from the initial attempt.

The offset search follows the frozen baseline's finite quantile-seeded,
multimode bracketing strategy and selects the lowest located
positive-curvature stationary loss. It verifies stationarity but is not a
formal certificate that every possible Student-t offset root has been found.
