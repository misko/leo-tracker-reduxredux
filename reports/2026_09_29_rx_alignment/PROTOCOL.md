# Omitted-pair receiver alignment: frozen exploratory comparison

Use all 913 training-selected pairs in the published 72-scan coherence census.
Do not change pairing, frequency units, masks, shape thresholds or held coverage.
This tests frequency alignment, not satellite identity or geographic position.

For each pair, fit a quadratic to the mean of RX0 and RX1 frequencies using
both-training matches only. Center time at its training median and scale by
10 seconds; subtract mean frequency for numerical stability. Require at least
five matches spanning five seconds, full rank and design condition ≤10,000.
The derivative of this polynomial supplies a training-estimated frequency-slope
feature at any target time. Its derivative is not an orbital prediction.

Calibrate each target with other selected pairs in the same scan/channel/exact
RF only. Remove every target-pair frequency difference from calibration. Require
at least four other pairs; every donor polynomial must qualify. Do not drop a
bad donor to rescue a fit. Sort donor IDs and use one equally weighted row per
pair: its training median frequency difference as response, training median
time and slope at that time as features.

Freeze seven arms: donor median (historical control), least-squares constant,
constant plus time drift, constant plus frequency-slope coefficient, both
features, and separate time/slope permutation controls. Permutation rolls the
relevant donor feature vector by one in sorted-ID order; responses and target
features remain unchanged. It is a training-feature negative control, not an
alternative physical trajectory or a causal forecasting experiment.

Center donor times at their mean, scale time by 100 seconds and slope by
1000 Hz/s. Use ordinary least squares with a rank/condition gate ≤1000; retain
all coefficients and gate failures. Reject, rather than clip or refit, solutions
with |drift|>20 Hz/s or |slope coefficient|>5 seconds. These are qualification
bounds on unconstrained fits, not a claim of constrained optimization. Intercepts
are not bounded. The donor-median arm must reproduce the published donor result
on the same eligible subset. No setting is chosen using a held score.

Predict a target difference at each held time from these frozen donor coefficients
and its training-derived slope feature. The target's held RX1 values condition
the RX0 frequency score; no held frequencies determine features or coefficients.
Score Student-t4 at scale 100√2 Hz and preserve median absolute error, 90th
percentile and the existing 100/300 Hz shape gate. Report per-arm coverage and
unavailable targets, and compare models only on identical targets/observations.
The primary shared population requires all five unpermuted arms to qualify;
permutation comparisons use their own explicit matched intersection. Do not
count unavailable controls as defeats or select models by coverage-adjusted scores.

Test injected constant, drift and slope effects, target-response exclusion,
held isolation, exact donor-median replay, insufficient donors, rank deficiency,
bounds and deterministic permutations before execution. Freeze sources and donor
result hash. One sequential process, BLAS1/nice19, 4 GiB and 90 seconds, with
≥5 GiB available RAM. Preserve failures without silently rerunning scientific
scores. No geographic fits, RF, raw IQ, bank/archive reads or production changes.

A slope coefficient has units of time, but is only a first-order alignment
coefficient. Clock offsets, estimator delay, frequency drift and wrong pairs
may be confounded; these data do not calibrate physical receiver timing. Rank
checks and synthetic recovery do not establish physical identifiability. The
population was selected by prior training coherence and is already explored;
any positive result needs a separately frozen geographic gate with unmatched
alternatives before claiming sub-km improvement.
