# Can phase instability predict unreliable CFO measurements?

**Not with the tested indicator on this arc.** Calibration-phase instability
does not improve held CFO uncertainty prediction. Its selected model assigns
larger uncertainty to three held dwells that actually have smaller CFO errors.
The result does not support using this phase statistic to downweight detections
in satellite association or position fitting.

This tests a distinct use of phase after the
[geometry comparison](2026_09_23_longarc_phase.md) and
[timing sensitivity](2026_09_23_longarc_timing.md) found no validated candidate
gain. It is a fixed-mean reliability screen, not a weighted association refit.

## Random nested validation

The same `scan-fw-f0af018448538a4c` episode supplies 78 dwells, with the frozen
seed-20260923 outer split of 42 training and 36 held whole dwells. Three inner
folds are assigned randomly within every temporal stratum among the outer
training dwells. No fold is a chronological interval. Each inner validation
dwell receives a candidate/affine receiver prediction fitted without that fold.

Features use only the local calibration-even frames in groups 0, 3, and 5:

- Phase consistency: equal-group resultant magnitude of doubled phase
  increments after subtracting adjacent-frame even-CFO phase advance.
- CFO-only control: even-CFO scatter around a local linear trend.
- Pilot control: rolled-pilot coherence from the same even frames.
- Permutation control: phase consistency permuted within temporal stratum
  and outer partition, with a recorded seed. Held features never enter the
  training permutation.

The phase feature requires at least two supported groups. All dwells qualify;
76 have all three groups. Unsupported calibration groups are explicitly
counted rather than converted into NaNs. Held odd measurements never choose
a feature, threshold, uncertainty scale, or response mask.

The uniform model's uncertainty scale is tuned on the same cross-fitted
training residuals as the feature models. Two-scale models permit equal good
and bad scales, so each can select the uniform null. This prevents ordinary
scale calibration from being credited to phase. The final mean prediction is
the previously frozen GLRT candidate 67330 plus its common affine receiver
offset/drift, identical for every uncertainty model.

## Held results

Every model scores all 36 held dwells with equal dwell weight. The Gaussian
negative log likelihood includes the scale normalization penalty; assigning
arbitrarily large uncertainty cannot improve the score for free.

| Uncertainty model | Selected scales, good / bad | Held NLL improvement over tuned uniform | Flagged held dwells |
|---|---|---:|---:|
| Tuned uniform | 150 / 150 Hz | 0 | — |
| Phase consistency | 150 / 250 Hz | -0.02892 | 3 |
| Even-CFO scatter | Equal scales | 0 | No effective downweighting |
| Rolled-pilot coherence | Equal scales | 0 | No effective downweighting |
| Permuted phase consistency | Equal scales | 0 | No effective downweighting |

The phase threshold is resultant magnitude 0.8. Its three flagged held dwells
have equal-dwell RMS **107.3 Hz**, versus **147.15 Hz** for the unflagged dwells:
the association between this flag and actual error has the wrong direction.
All methods retain the same mean prediction and therefore the same overall
held CFO RMS, **144.254 Hz**. The likelihood degradation is a degradation of
uncertainty prediction, not a new position-error measurement.

The [artifact](figures/2026_09_23_longarc_phase/reliability.json) records the
training-selected configurations, random fold assignments, features, per-dwell
held likelihoods, coverage, and provenance. No held dwell was removed to improve
the result, and no satellite identity or position improvement is claimed.

## Scope and next evidence

The result is specific to this source hypothesis, receiver, sample rate, and
50-second arc. A different source or calibrated receiver may behave differently.
It does not imply that phase-slip detection is generally useless; it shows that
this particular calibration-phase indicator does not predict the dominant
held error here. Shared trajectory mismatch still dominates the CFO residuals.

A useful next association study needs a separately frozen arc or source cohort,
with a matched mean model and the same controls. Repeated tuning of these 36
held dwells would turn them into development data without establishing general
improvement. A geometric dual-receiver constraint additionally requires the
electrical baseline, receiver identity, same-source pairing, and phase stability
authorities described in the [geometry audit](2026_09_23_phase_geometry_observability_audit.md).
Production association and position estimators are unchanged.

Reproduce with `tools/research/evaluate_longarc_phase_reliability.py` in the
numerical environment and `PYTHONPATH=src:tools:.`. Owned tests cover random
within-stratum inner folds, isolation from outer-held residuals, the likelihood
scale penalty, and inclusion of the full uniform-scale null. All four pass;
together with the timing tests, all 11 focused tests pass. Ruff and diff checks
pass.
