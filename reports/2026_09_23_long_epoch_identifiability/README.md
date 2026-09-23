# Epoch flexibility versus local position information

Adding epoch corrections can improve residuals while removing distinctions
between receiver positions. This TRAIN-only audit quantifies that tradeoff at
the two sealed six-scan baseline locations, with identities and visibility fixed.
It is a linearized objective diagnostic, not calibrated Fisher information,
a position covariance, or a CRLB.

Each track's training-only constant CFO is projected out. We retain the 461
tracks below the 800 Hz cap; the 15 already capped tracks contribute no local
gradient. Duration-weighted Doppler derivatives form a two-coordinate position
matrix. Profiling either six scan epoch terms or 117 active satellite epoch
terms gives its Schur complement. The epoch penalty is exactly the existing
`800^2 / scale^2` coefficient. There are no jointly fitted scan and satellite
terms in this comparison, so it does not introduce their additive gauge.

| Nuisance family | Scale | Position curvature retained, weakest / strongest normalized direction |
|---|---|---:|
| Scan | 0.2 s | 38.1% / 90.6% |
| Scan | 1 s | 5.9% / 86.0% |
| Scan | 5 s | 3.9% / 85.8% |
| Scan | Unregularized | 3.8% / 85.8% |
| Satellite | 0.2 s | 78.3% / 84.7% |
| Satellite | 1 s | 21.0% / 36.1% |
| Satellite | 5 s | 3.3% / 19.4% |
| Satellite | Unregularized | 1.8% / 16.7% |

These Sacramento values closely match Reno. Changing the central epoch
difference step from 0.05 s to 0.01 s changes the directional fractions by less
than 0.000007. Position differences use ±0.1 km east/north about each fitted
point. Directions are generalized eigenvectors relative to the baseline
position matrix, not fixed east/north axes.

![Profiled curvature](profiled_curvature.png)

Weakly regularized satellite effects can absorb much of the variation that
localized the receiver, especially compared with tightly regularized satellite
effects. That does not prove the model will give worse positions: correcting
real bias may still help. It does mean that residual improvement alone cannot
justify accuracy, and that fitted positions may depend strongly on regularization.
The nonlinear fit must report this sensitivity and be checked on independent
recording groups.

The calculation is local, ignores residual second-derivative terms, and freezes
candidate choices, visibility and cap membership. It does not model independent
sample counts or orbital-error covariance. The conditional information fractions
must not be converted into a metre-level accuracy claim.

Reproduce from the repository root:

```bash
.venv/bin/python reports/2026_09_23_long_epoch_identifiability/audit.py
.venv/bin/python reports/2026_09_23_long_epoch_identifiability/plot.py
```

`results.json` binds the source, selected baseline, cohort and epoch helper.
The baseline binds the underlying causal caches. A focused test compares this
blockwise calculation with a dense Schur complement and checks monotonic
strengthening with regularization. No reference, validation or test outcome
is used.
