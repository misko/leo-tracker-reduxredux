# Unknown antenna height can alias into horizontal position

The baseline fixes receiver ellipsoidal height to zero. The station authority
explicitly records altitude and datum as unknown, so no independent correction
can currently be selected from that metadata.

A local conditional geometry calculation gives the following horizontal alias
for a hypothetical 100m true-height change while fitted height remains zero:

| Scan | Equal-weight alias | Positive IRLS-weight alias | Remaining height information fraction, equal / IRLS |
|---|---:|---:|---:|
| 0 | 324.4m | 348.9m | 0.611 / 0.619 |
| 16 | 41.5m | 33.5m | 0.977 / 0.994 |

Each track is conditioned on its original training-MAP satellite and centered
to remove a constant CFO. Height sensitivity is projected on east, north and
timing derivatives. The coefficients describe how a true height perturbation
could be absorbed by the zero-height fit locally. They do not estimate actual
height or predict the error reduction from applying a correction. Re-fitting
with a different fixed height would have the opposite first-order compensation
sign under these approximations.

Neither weighting is the observed profiled mixture Hessian. Positive IRLS
weights omit residual-curvature and mixture terms. Source correlations,
ephemeris error and conditional association remain unmodeled. The retained
height-information fractions are design projections, not calibrated precision.

All 120 tracks and 4,046 training rows enter this audit. Zero-height predictions
reproduce the baseline exactly; height derivatives from 1m and 10m steps agree
within 3.07e-7Hz/km. Two tests cover exact alias, orthogonal information and
weight scaling. All 127 bound source hashes verify. No geographic reference,
altitude estimate, position fit, or new orbit data enters the calculation.

The next evidence needed for a physical fixed-height correction is independent
antenna altitude with its vertical datum. This audit makes that measurement
more relevant than the previously checked light-time correction, but does not
justify choosing a height from DS11 geographic errors.

See [protocol](PROTOCOL.md) and [complete results](outcome.json).
