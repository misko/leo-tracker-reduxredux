# Donor-calibrated element-age scale fails its matched-control gate

The single frozen element-age arm passes numerical qualification and predicts
held residuals better than the original fixed 100-Hz scale, but it does not
beat the donor-fit constant-scale control in every dataset. The declared gate
therefore fails. No DS11 residual, reference coordinate, model, or geographic
fit was used or launched.

The donor fit is

`sigma(age) = sqrt(100^2 + (113.392750 age_days)^2) Hz`.

The matched age-independent donor fit is `sigma = 142.319415 Hz`. Both scalar
optima are successful, finite, interior, and pass derivative audits. At the
frozen target cases, the age arm spans 102.616--471.768 Hz.

| Held comparison | DS7 | DS8 | DS9 | Source wins |
|---|---:|---:|---:|---:|
| Age minus fixed 100 Hz | +0.081958 | +0.111980 | +0.224600 | 1327 / 2512 |
| Age minus fitted constant | +0.000099 | **-0.000301** | +0.056937 | 1306 / 2512 |

Values are hierarchical mean nats per held observation: observations within
case, tracks within physical source occasion, sources within scan, scans within
dataset. The arm clears the fixed-100 comparison in all three datasets and a
majority of source occasions. It misses the matched-control requirement in DS8,
so the positive DS9 effect and overall majority cannot promote it.

The preflight resolved exact element epochs from pinned provider snapshots and
replayed all 9,968 donor cases. Maximum position, velocity, and reconstructed
frequency differences are all exactly zero. All 3,983 cases in the nine
disjoint target panels match the earlier zero-difference target replay. The
preflight completed in 84.41 seconds and the calibration/transfer job in
107.45 seconds, each under its separate 180-second single-worker cap.

At fixed 100 Hz, the new finite-root profiler matches the frozen fast baseline
to 4.66e-10 Hz in offset and 4.55e-13 in training score on donors; target
differences are 4.66e-10 Hz and 3.41e-13. Its normalized t4 density also matches
SciPy's normalized density in component tests. The root enumeration follows
the baseline's finite quantile/start/bracket procedure; it is not a mathematical
certificate of the global profile minimum for arbitrary residual arrays.

This result mirrors the caution from the earlier RX-scale experiments: a
variable scale can beat fixed 100 Hz yet fail to beat a one-parameter constant
control under the transferred predictive target. The age relation remains a
descriptive conditional residual association. No broader age law, cutoff,
scale sweep, retry, RF collection, archive mutation, or production edit was
performed.

Artifacts: [protocol](AGE_SCALE_PROTOCOL.md),
[exact bindings](age-bindings.json), [calibration](age-calibration.json),
[likelihood implementation](age_scale.py), and [tests](test_age_scale.py).

