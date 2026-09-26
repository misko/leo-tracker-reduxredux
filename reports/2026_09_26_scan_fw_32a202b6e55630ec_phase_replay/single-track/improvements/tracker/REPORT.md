# Causal differential phase tracking

This bounded experiment uses the frozen pilot cache for dwells 259–263. All
methods estimate differential phase from simultaneous `RX1 * conj(RX0)` pilot
channel products after the unchanged coarse GLRT branch correction. Fits use
even tone indices 0, 2, 4 and 6. Odd indices 1, 3, 5 and 7 are scored without
an odd-tone phase-intercept calibration.

The cache contains 445 frames: 70 whose full symbol support ends by 20 ms,
371 whose support starts at or after 20 ms, and four boundary-crossing frames
excluded from both frozen sets. The odd-tone split is a differential-phase
holdout: the upstream RX0-only shared residual estimator used all eight tones.

## Two distinct prediction questions

The frozen early-window experiment fits each dwell's 14 early frames once and
forecasts the following approximately 100 ms. The GLRT-only baseline holds the
early phase constant; the frequency model is linear phase; the frequency-rate
model is quadratic phase. Configurations were fixed before held scoring.

The rolling experiment predicts one frame ahead, normally about 1.333 ms. It
emits a prediction before reading the current frame. A current innovation over
2.1 rad is therefore counted as an error, then starts a new unsupported segment
for subsequent predictions. Gaps are never bridged. Previous-phase and
two-frame wrapped-increment baselines expose how much of the result comes from
the short horizon.

## Result

The frozen 100 ms forecast fails to recover a slow, stable held-tone phase.
Across all 1,484 held odd-tone samples, wrapped RMS is 113.00 degrees for the
GLRT-only constant phase, 94.88 degrees for constant differential frequency,
and 101.57 degrees for smooth frequency/rate. The quadratic model is worse than
the linear model and its fitted rates are unstable across dwells, so there is
no support here for treating early-window curvature as satellite motion.

The rolling robust result is reported separately because its horizon is much
shorter. Its gate-conditional RMS is 46.55 degrees on 365 of 371 held frames.
Charging the six unsupported frames the maximum wrapped error of 180 degrees
gives a failure-inclusive RMS of 51.54 degrees. The causal minimal baselines in
`tracker-results.json` do much better: 27.72 degrees for previous phase and
21.68 degrees for the previous two-frame wrapped increment, both on all 371
held frames. Thus the robust rolling fit adds no value here; the improvement
over frozen forecasts comes from its short horizon, and even the simplest
causal extrapolator beats it. No held-data model selection or response
flattening is performed.

These absolute odd-tone errors include real frequency-dependent receiver and
propagation phase because no held-tone intercept is removed. That makes the
test deliberately hard and prevents a smooth-looking curve from being created
by calibrating the evaluation target. It also means these RMS values should not
be read as pure frequency-tracker error.

## Reproduction and artifacts

Run `run.py` with the pinned scientific runtime. `tracker-predictions.csv`
contains every frame/model prediction, uncertainty, support flag, segment and
held-tone frame RMS. `tracker-results.json` records cache hashes, preprocessing
qualification, per-dwell results, conditional metrics, and failure-inclusive
aggregates. Synthetic tests inject frequency, frequency rate, a gap, a cycle
slip, missing tone evidence, and current-frame perturbations to verify causality.
