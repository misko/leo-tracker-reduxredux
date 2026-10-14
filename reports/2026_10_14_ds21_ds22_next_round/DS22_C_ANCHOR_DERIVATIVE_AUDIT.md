# Rejected C anchor profiles: derivative audit

All three rejected profiles have real residual derivatives in the tested directions. The audit used their sealed endpoints, original full C models and fixed geography. It ran zero optimizer calls and 27 diagnostic objective evaluations: nine on DS22-003 and eighteen on DS22-001, excluding original-model reconstruction/replay. No reference or held data entered the diagnostic.

| Case / anchor | Physical stationarity | Largest scaled receiver derivative | Largest tested free physical derivative | Central difference, step 1e-5 |
|---|---:|---:|---:|---:|
| 001 / lower | 1198.827934 | 867.428927 | 1195.018566 | 1195.018565 |
| 001 / upper | 294.249491 | 280.027767 | 295.332061 | 295.332059 |
| 003 / upper | 0.002957262 | 0.000924607 | -0.001229213 | -0.001232547 |

Both central-difference step sizes (1e-5 and 1e-6 in optimizer coordinates) were feasible in every tested direction. Receiver derivatives also agree with finite differences. This supports the independent rejection criterion and provides no evidence of a gross derivative implementation error in these directions; it is not an exhaustive gradient proof.

The two 001 profiles exhausted their 20-second allowance far from stationarity. The 003 upper profile stopped with solver success after 15.272 seconds but still exceeded the 0.001 independent stationarity threshold. It had a much lower objective than the accepted release, so its failed convergence is consequential to the attempted comparison. It remains excluded.

Next experiment: a separately frozen, explicitly additional-budget checkpoint control. Review and preserve all original call receipts. From each of the three rejected endpoints, allow exactly one further 20-second/600-iteration fixed-position fit and, only if stationary, one 20-second/600-iteration release. Apply the same profile/release allowance to the original full-band endpoint on each case. Keep each original anchor, 25 km domain, candidate bank, model, priors and fitted c unchanged; any tiny timing initialization margin must be recorded and bounded as in the original qualification. Select only stationary releases by the unchanged training objective, seal both cases before reference reporting, and retain every failure without another continuation. Maximum ten new calls across both cases. This distinguishes incomplete profile optimization from a model preference; it is not an equal-total-budget comparison with the original six-start matrix and cannot by itself validate full-cohort accuracy.

Provenance: frozen audit source `a17294919`; four directional-selection unit tests pass, Ruff passes. The first audit version (`f72a72f3c`) failed on 003 before any diagnostic objective evaluation because it treated the qualified-plan wrapper as the starts mapping. Its failed receipt is retained under `local/ds22-c-anchor-stationarity-v1/DS22-003`; no scientific fit was attempted. Version 2 checks the complete qualified plan against the sealed original and completed both cases under `local/ds22-c-anchor-stationarity-v2`.
