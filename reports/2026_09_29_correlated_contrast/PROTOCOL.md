# Correlated contrasts with an explicit unassociated trend

Freeze two new geographic arms on the same eighteen consecutive DS7/DS8/DS9
early/middle/late four/eight panels: corr10 without a cone and corr10_c40 with
the existing soft40 cone. Both keep q=0.20, noise scale 100 Hz, slope scale
2000 Hz/s and Student-t4 errors. Correlation decay is fixed at ten seconds,
with the existing 0.2 nugget. No parameter is selected by reference errors.
The published zero-decay q020 and soft40 results are matched historical controls.

Let K_ij = 0.8 exp(-|t_i-t_j|/10) + 0.2 I_ij. For anchored differences D,
the satellite scale matrix is 100² D K Dᵀ. The background scale matrix is
100² D K Dᵀ + 2000² (Dt)(Dt)ᵀ. Both are normalized densities in the same
n−1 frequency differences. Constant frequency is eliminated; no offset is
estimated using held observations. Whitening and a rank-one decomposition
avoid cancellation in the broad-slope background. Zero decay means K=I.

Keep each satellite trajectory, shared location, and one timing offset per
scan. Soft40 keeps fixed nominal west/east ±10-degree axes, 40-degree
half-angles and a 2-degree sigmoid edge, with rejected satellite prior mass
routed to background. The axes and cable mapping remain uncalibrated. The
retained training-visible bank is not the full catalogue. K=0 abstains.

Training geometry, visibility and priors determine both training and joint
densities. Held scores are joint-minus-training log density; held measurements
must not alter training weights. No reception/non-reception likelihood or
verified cross-RX identity is claimed. Both geographic arms remain soft models.

Before fitting, ten tests must pass: independent rational covariance oracle
at every anchor, zero-decay signal/background replay and translations,
density derivatives, invalid scales and repeated times, whole-model replay at
q=0/.2/1, all position/timing derivatives with/without cones, held isolation,
conditional predictive integration, unit-background zero force/empty-bank
abstention, and fresh-process imports. During development, the new polynomial
test wrapper needed candidate-count metadata and the matrix oracle needed
exact rank-one assembly before elimination. The resulting oracle uses a
stricter 1e-10 comparison; published fixtures were not modified.

Use four starts per panel/arm: E/N (0,0), (3,-3), (-3,3) km with zero timings,
plus that panel's published q020 training-selected fit. Bounds E/N ±12 km,
timing ±5 s. L-BFGS-B maxiter140, maxfun200, ftol1e-14, gtol1e-8, maxls30.
Qualify successful fits with gradient infinity norm ≤0.01 and all coordinates
at least 0.001 from boundaries. Select highest training score only. Retain
generic-only selection alongside the four-start selection in the report.
Never retry completed fits or substitute after a selected audit fails.

Replay selected training scores within 1e-7. Audit every coordinate at two
steps: E/N 0.001/0.0005 km and timing 62.5/31.25 microseconds. Every derivative
discrepancy must be <0.002; timing stencils must not cross quarter-second nodes
and must agree within 0.002. Candidate visibility must remain unchanged.
At each selected location, the zero-decay version must replay the published
implementation's training score, gradient, held scores, signal responsibilities
and candidate weights within 1e-7. Require probability sums within 1e-10.

All 36 planned units and every start/failure belong in the final report.
Separate numerical qualification, held prediction and geographic error. Each
dataset/size median requires all three block audits. Retain late DS9, worst
errors and nominal sub-km counts; no geographic result is a surveyed accuracy
or calibrated resolution claim. The inherited origin is already 809 m from
the exposed reference. These explored, nested panels are not independent trials.

Use one worker, BLAS1/nice19, 4 GiB address-space cap, 180 seconds per child,
and ≥5 GiB available RAM before launch. Execute bounded batches; do not launch
a multi-hour campaign. Bind source/input artifacts before fitting and verify
each child's sources and inputs before/after execution. No RF collection,
raw-IQ processing, propagation, provider fetch, archive reads or production
changes. A partial report must name pending units and cannot claim completion.
