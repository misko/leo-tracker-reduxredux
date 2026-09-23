# Local phase resolution audit

The failed 100 microsecond replay does not rule out a coherent 20 ms
coefficient measurement. It rules out its sixteen-coefficient per-group phase
trajectory as predictively stable in the reused 28.2 s development snippet.

Each group retains 218 samples after the 16-sample guards at 2.5 MS/s. It fits
16 complex coefficients per receiver: two sources times eight tones. Full rank
16 and maximum design condition 1.72 show no numerical singularity. They do
not yield pilot SNR or coefficient covariance.

Exact held affine residual RMS is 1.300 rad and resultant is 0.462. The minimum
projection coherence 0.030 is one worst held group, not an average coherence,
SNR, or phase-variance estimate. No retained artifact has noise power,
coefficient covariance, or coherent pilot energy. The held residual 10th and
90th percentiles are −1.216 and +1.741 rad. This estimator is far from
microradian resolution.

## Integration limit

If all 200 groups had independent zero-mean phase error, 20 ms combining would
reduce 1.300 rad by `sqrt(200)` to about 0.092 rad. This is an optimistic
scaling calculation. Correlated phase motion, source leakage, or mismatch will
not average. It still shows that the local result does not prove the existing
20 ms joint waveform fit cannot estimate one static differential phase.

One fixed measurement-floor endpoint could clarify this. Before IQ access,
freeze a 20 ms coherent extraction using existing nominees, edge, absolute
sample gauge, and independent CFOs. Fit two-source/eight-tone coefficients
separately on the existing seeded random training and held groups. Form a
transported same-time cross-receiver/source difference for each split. Bootstrap
whole groups within each split for circular uncertainty. Report every tone,
rank, condition, rolled-pilot and swapped-epoch controls. This is not a
bin-width search. It measures static integrated-phase repeatability, not motion.

## Geometric implication

The 8 cm sensitivity audit bounds short-dwell geometry at 0.00946 rad after a
free phase intercept and 2.045 microradians after free intercept plus
differential frequency. Even 0.092 rad is about 45,000 times the latter. It is
not a demonstrated noise floor. A repeatable short-dwell phase still cannot
constrain geometry after phase/rate nuisance fitting.

The counterfactual 39 s calculation retains up to 0.284 rad after one global
affine nuisance. That scale could discriminate candidates only after proving a
counter-qualified continuous two-source interval, fixed template gauge, and
receiver phase/frequency-response transport. Present corpus authority lacks
those facts. The order is: frozen 20 ms floor test, then separately selected
multi-second intervals with seeded random whole-interval outer holdouts and
wrong-time/source-pair controls. Such a test can show conditional candidate
compatibility. It cannot show position or velocity without baseline and channel
calibration.

Sources: [local result](figures/2026_09_23_local_differential_phase/result.json),
[local report](2026_09_23_local_differential_phase_results.md), and
[8 cm sensitivity audit](2026_09_23_phase_geometry_sensitivity.md).
