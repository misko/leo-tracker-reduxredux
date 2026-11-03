# Local geometry and conditional label ambiguity do not explain the full accuracy gap

At the12frozen all-data baseline states, freeing clock, receiver drifts and
active satellite epochs retains median60.6%of prior-supported position
information in the least-retained direction and80.5%in the most-retained
direction. The local two-dimensional position block remains positive. This
does not support a complete local loss of geographic information, though
several scans depend materially on nuisance priors.

The most affected scans are DS10-F028 (24.7%/48.2%retention) and DS9-F025
(25.5%/57.1%). Prior-supported inverse-curvature major-axis scales span616–1335m.
These are conditional IRLS scales, not calibrated error bounds. Removing priors
at a fixed fitted state is a geometry diagnostic, not a newly fitted model.
It does not establish global uniqueness or the correct satellite identities.

![Nuisance-free position information](position-observability-v1.png)

The calculation whitens each fixed-identity Jacobian by its noise covariance
and positive Student IRLS weight. It projects position columns onto the
orthogonal complement of nuisance columns, using column normalization before
SVD. Rank agrees at two tolerances. The prior-augmented projection independently
agrees with a Schur-complement calculation. Every scan has the expected single
clock/epoch nuisance gauge; this confirms a known symmetry rather than revealing
a new geographic degeneracy. Two tests check rescaling invariance, exact
confounding and generalized-eigenvalue arithmetic.

## Conditional satellite-label diagnostic

For the three fixed pilot scans, compute the covariance of alternative-label
log-likelihood gradients along the local position displacement accompanied by
optimal linear nuisance compensation. This is the missing-label term in a
mixture Hessian, compared here with the hard-assignment IRLS position matrix.
It is not a full observed-curvature calculation or calibrated covariance.

| Scan | Gradient-spread / hard-IRLS information eigenvalues | Tracks with maximum label probability below90% | Tracks above99% |
|---|---|---:|---:|
| DS9-F025 | 2.77%,5.27% | 6 | 40 |
| DS10-F028 | 3.25%,10.72% | 8 | 30 |
| DS11-F018 | 0.36%,1.41% | 6 | 42 |

This conditional ambiguity is modest relative to the local quadratic. It does
not rule out confidently wrong identities or remote association/location modes:
incumbent satellite epochs are optimized, inactive alternatives are not, and
probabilities are evaluated at the current fitted state. Tiny branches below
1e-10probability are omitted (total omitted mass below1e-6) and weights
renormalized; this does not bound their gradient contribution. Catalogue
visibility discontinuities are outside the local calculation.

## Evidence review and next experiment

The earlier DS7 slope-identifiability report also found uneven but nonzero
local position information. It used a different model and dataset; it cannot
substitute for the present DS9/DS10/DS11audit. The early fixed-reference DS10-F056
diagnostic stopped allthree starts at their time limits, so its higher reference
objective cannot settle model mismatch versus incomplete optimization.

Next, use the current bounded, scaled solver for an explicitly reference-informed
offline nuisance-profile diagnostic, with original baseline identities held
fixed. Compare reference and fitted-location residual contributions by satellite
group after convergence. This can reveal whether a few groups drive the mismatch
or whether it is diffuse. It cannot establish the best association at the
reference or be counted as a localization result. Preserve the Sacramento prior
and GPS-free initialization/association rules in every actual estimator.

Do not infer that stronger nuisance priors, simple label softening, or another
frequency-noise calibration will solve the kilometer errors. The current
evidence supports a targeted residual/model diagnosis before another sweep.

The observability audit took15.20seconds and the conditional-label audit5.00
seconds. Neither fitted a location, read reference coordinates or collectedRF.
The original64benchmark and its error metrics are unchanged; no held-out or
uncertainty-calibration claim is added. Evidence is in
`position-observability-v1.json`, `label-gradient-spread-v1.json`, source/input
bindings and SHA256 sidecars.
