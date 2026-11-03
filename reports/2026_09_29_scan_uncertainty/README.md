# Local fit curvature understates the scale of cross-scan disagreement

The N24 fits have narrow local curvature, but substantially larger sensitivity
to the observed disagreement among scans. Including scan-level score variation
increases local axis scales by generalized factors of 5.6–13.1 relative to
inverse curvature. This explains why numerical convergence and a sharp local
optimum alone cannot certify reliable sub-km performance.

| Dataset | Curvature-only axis scales | Scan-group axis scales | Time-window-group axis scales |
|---|---:|---:|---:|
| DS7 | 51 / 66 m | 417 / 798 m | 99 / 1,259 m |
| DS8 | 46 / 61 m | 395 / 440 m | 209 / 740 m |
| DS9 | 50 / 76 m | 357 / 533 m | 138 / 454 m |

Each cell lists the smaller and larger square-root covariance eigenvalues.
Axes may rotate between methods; dividing corresponding table entries is not
a same-direction inflation calculation. These are local sensitivity proxies,
not validated standard errors, confidence intervals or measured position errors.
The window estimate uses only three groups and is particularly unstable.

## What was computed

Use all 72 source scans and the previously audited training gradients and
observed negative Hessians at each dataset's unchanged N24 fit. Each scan's
timing nuisance is locally profiled out. Let H be summed geographic curvature
and g_k the score of group k. The two covariance constructions are:

```
curvature-only: inverse(H)
group-score:    inverse(H) × [K/(K−1) Σ (g_k−mean(g))(g_k−mean(g))'] × inverse(H)
```

For scan groups, K=24. For time-window groups, sum scores within each frozen
eight-scan early/middle/late window, then use K=3. The K/(K−1) correction is
explicitly part of this diagnostic; it does not establish calibrated fitted
mixture degrees of freedom. Scores, source location and grouping are unchanged.
No held observations, target prediction or geographic reference select a result.

The generalized scan-group scale inflation ranges are 7.56–13.12 for DS7,
6.62–9.33 for DS8 and 5.64–8.91 for DS9. These account for axis rotation by
comparison in the pooled-curvature metric. [Results](results.json) retain
the matrices, eigenvectors, inflation values and aggregate score sums.

## What this does and does not imply

The discrepancy supports treating within-scan dependence and between-scan model
disagreement as material. It does not distinguish orbit error, receiver effects,
association mistakes, noise miscalibration or geographic bias. The scan-group
construction still relies on an independence assumption between groups if used
inferentially; temporal and satellite recurrence can violate it.

Grouping by time window increases the largest axis for DS7 and DS8 but decreases
it for DS9. With only three windows, neither outcome certifies a physical
correlation structure. Do not take the maximum as an automatically calibrated
conservative bound, or interpret the smaller DS9 value as evidence of less error.

Score-balanced subset compression preserves the pooled solution and its local
score cancellations. It does not remove this disagreement or independently
validate accuracy. Likewise, no required scan count can be inferred here by
assuming uncertainty shrinks as the inverse square root of scan count. That
assumption needs validation across independent time/site groups first.

## Verification and next decision

The source evidence seal verifies before loading. All 72 upstream scan audits
qualify, pooled curvature and resulting covariances are positive definite, and
window/scan score sums agree. Two synthetic tests recover the known mean-model
variance and show that duplicating data within fixed clusters does not create
false additional precision. Ruff passes. No new fit is run.

Do not use curvature-only uncertainty as a sub-km acceptance or early-stopping
criterion. The next useful validation should compare location stability across
disjoint time groups and independent reference measurements while retaining
the original model as control. A physical calibration must demonstrate transfer
before smaller reported covariance is accepted as improved accuracy.

See [protocol](PROTOCOL.md), [study](study.py) and
[preceding source disagreement audit](../2026_09_29_scan_disagreement/README.md).
No RF collection, production changes or publication occurred. Artifacts are
local. Reproduce with `study.py` under NumPy in a fresh output context.
