# Correction: GLRT parameter rankings depend on the evaluation reference

The previous reports do **not** establish that the deployed GLRT parameters
are optimal or most accurate. Their RMS metrics measure consistency with
observed CFOs and a fitted model, without independent frequency ground truth.
This note qualifies the parameter recommendations in the earlier sealed
reports; their recorded measurements remain unchanged.

## What was treated as the reference

- Full-fit RMS compares measured CFOs with a cubic fitted to those measurements.
  It measures smoothness around that model and cannot establish absolute bias.
- Window/grid replay fits each variant's measurements and predicts held-out
  measurements from that same variant. It measures conditional predictability,
  with acquisition seeds, alias branches, and selected tracks inherited from
  the original configuration.
- Stride replay trains on each proposed probe schedule but evaluates every
  schedule against first-probe measurements from the current configuration.
  Entire held-out visits are excluded from fitting, but the reference favors
  the measurement population selected by the current configuration.
- The separate orbital fits provide a physical consistency check. Satellite
  associations are candidates selected using these data, with fitted timing
  and frequency nuisance parameters; those fits are not independent truth.

A cubic can absorb a constant or slowly changing estimator bias. It can also
leave residuals caused by real departures from a cubic, clock behavior, or
incorrect track membership. Low residual RMS therefore does not uniquely
identify a more accurate estimator.

## Reference sensitivity check

Using the existing wider-timing replay, keep exactly the same cubic training
data, fit weights, and visit-grouped three-second folds. Change only the
held-out evaluation targets: first-probe measurements versus all six
nonoverlapping positions at 0, 20, ..., 100 ms. Do not margin-filter evaluation
targets. Each held-out visit contributes equally to the combined target metric.

| Training stride | Median block RMS against first position | Median block RMS against all six positions |
|---|---:|---:|
| 120 ms | 78.6 Hz | 157.3 Hz |
| 60 ms | 102.5 Hz | 158.0 Hz |
| 40 ms | 87.6 Hz | 157.3 Hz |
| 20 ms | 90.3 Hz | 152.2 Hz |
| 10 ms, all probes in research fit | 92.2 Hz | 152.4 Hz |

**The ranking changes when the reference changes.** Against the broader target,
20 ms stride has a paired geometric RMS ratio of 0.986 relative to 120 ms,
with a 95% scan-bootstrap interval of [0.972, 1.001]. This is inconclusive
and does not establish that the denser stride is better. All these targets
still inherit the original acquisition seeds, and none is independent truth.
The 120 ms first-position result reproduces the original 78.605784 Hz metric
within 0.000001 Hz; every fit excludes all probe positions in held-out visits.

Per-track values, all individual target offsets, and paired intervals are in
`target-sensitivity.json`. This is a diagnostic audit of reference dependence,
not a new tuning/validation split or a production recommendation.

## What a stronger comparison needs

Use known-frequency/rate signal injections to measure estimator error directly,
with several signal strengths and real recording backgrounds. Controlled
frequency shifts of real recordings additionally test relative response, but
cannot reveal an unknown original frequency bias. Independently acquired,
disjoint pilot/frame estimates can test reproducibility on real signals.

For orbital validation, fix satellite association and allowed clock/frequency
calibration using separate data, then score untouched observations. Keep
orbital/clock-model mismatch distinct from short-timescale measurement scatter.
Hold out entire scans for final parameter comparisons and measure discovery,
track retention, wrong associations, and compute alongside RMS.

Until then the supported conclusion is limited: the current settings performed
well under a particular conditional smoothness/prediction test. We have not
demonstrated that they are the best parameters for true Doppler accuracy.
