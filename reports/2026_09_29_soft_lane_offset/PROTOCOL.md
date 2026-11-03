# Soft receiver/RF offset prototype

Frozen before geographic fits. Use the nine existing DS7/DS8/DS9 early,
middle, and late eight-scan panels and their unchanged training/held masks.
All retained candidate mixtures, visibility gates, Student-t4 frequency
contrasts, and 20% unassociated trend background remain in the model.

Add a wrapped Cauchy prior for each track's native-Hz offset, centered on a
fitted recording/RX/exact-RF lane mean. Test fixed widths 3,000 and 10,000 Hz,
motivated by the preceding lane-transfer audit; do not select by geographic
error. Period is 1/4.4 microseconds. Marginalize the track offset using its
conditional t_(n+3) distribution under the flat-offset contrast model.
Use 64-point quantile quadrature, auditing against 128 points.
Background offsets are uniform over one period. Omit the common uniform
density constant in both models; score held observations as full minus train
joint mixture log likelihood, with the fitted lane means unchanged.

Initialize position/times from the cached baseline. Initialize each lane's
mean with the circular mean of its training-MAP candidate residual offsets.
This initialization uses no held values or location reference. Fit one local
start per width, E/N within +/-12 km, timing within +/-5 seconds, lane means
unbounded (periodic). Maximum 100 iterations and 160 evaluations, 120-second
wall cap per panel/width. Report incomplete and unqualified fits explicitly.
Qualify only optimizer success, projected gradient <=0.01, no geographic or
timing boundary, finite-difference gradient discrepancy <=0.02, and quadrature
score discrepancy <=0.01 with maximum gradient discrepancy <=0.01.

The inherited exposed, unsurveyed location reference is used only after
fitting. This is a local retained-bank feasibility experiment, not proof of
general accuracy. No RF collection, measurement changes, or production edits.

## Numerical amendment after the first pilot

The original DS7 early/3-kHz pilot hit 100 iterations (projected gradient
2.49), despite passing derivative and quadrature checks. Its output is
preserved as `pilot_unscaled.json`; it is not an accuracy result. Before
running the remaining panels, scale optimizer variables by 1 km for E/N,
0.1 second for time, and the prior width for lane offsets; retain physical
gradient qualification. Increase the iteration/evaluation caps to 300/400
and L-BFGS history to 30, retaining the 120-second wall cap. This amendment
addresses convergence and does not select a model by geographic error.
