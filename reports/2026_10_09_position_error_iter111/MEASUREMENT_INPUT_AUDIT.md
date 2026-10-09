# Orbit-blind frequency repeatability: available inputs

Source/contracts and published-report inspection only. No recording inputs,
reference values, reserve outcomes, raw IQ, numerical replay or optimizer were
read or run. No experiment is frozen and no uncertainty model is proposed for
deployment. This audit asks what can actually support the measurement-precision
idea already described in iterations86/106.

## Public fields: available is not calibrated

| Quantity | Existing public path | Limitation |
|---|---|---|
| Measured CFO | `TrackingCandidate.fractional_tracking_cfo_hz` | A point estimate; no candidate-specific CFO variance in this port. |
| Detector quality | Fractional exact score, control score, margin, rank and margin-pass flag | No declared conversion to SNR or frequency-estimator variance. GLRT margin is not calibrated SNR. |
| RF/sample timing | `TrackingProbe.actual_rf_hz`, receiver, channel, edge, visit/probe index, probe start, valid device counter; `TrackingInput.sample_rate_hz` and UTC authority | Actual tuned RF is available. This is not the observed emitter's exact transmitted center frequency. |
| Nominal window | `TrackingInput.probe_ms`, default20 ms | A nominal probe duration, not the duration of uniformly weighted frequency-estimator support. |
| Physical support | Projected candidate source sample bounds, UTC support start/center/end and factorial support moments | Reconstructible from persisted epoch/offset and known GLRT support geometry; not independent repeat measurements. |
| Named uncertainty | Projected `PersistentHopCfoCandidate.standard_uncertainty_hz` | Assigned globally from a400 Hz base plus UTC bracket/rate allowance, not estimated per-window RF precision. |
| Final positioning rows | `PositionObservations`: window ID, time, measured CFO, RF, receiver, channel, margin | Does not carry variance, calibrated SNR, physical support duration or moments. |

The concrete interfaces are
[TrackingCandidate/Probe/Input](../../src/leo/contracts/scanner_tracking.py),
[the manifest-verified public source adapter](../../src/leo/storage/scanner_tracking_source.py),
[candidate projection](../../src/leo/application/scanner_trajectory.py),
[projected candidate contract](../../src/leo/analysis/persistent_hop_trajectory.py),
and [position observations](../../src/leo/contracts/regional_position.py).
The source adapter opens capture/analysis stores read-only and copies declared
candidate fields. Its adaptive default probe stride is120 ms; it supports other
explicit strides. This source-level availability is not a census proving that
every historical member has each optional field or compatible provenance.

Projection sets
`standard_uncertainty_hz = hypot(400, 15000 * first_sample_bracket_width_ns / 2e9)`.
It therefore mixes a fixed frequency allowance with capture-level time uncertainty
under a rate bound. It cannot be reused as a measured heteroscedastic variance,
and its timing contribution can be correlated across the capture.

[Support reconstruction](../../src/leo/application/persistent_hop_trajectory.py)
uses the actual fractional epoch, sample rate, selected GLRT64 symbol intervals
across frames and interpolation guards. It averages symbol-support centers and
retains second/third factorial moments. The outer sample interval bounds the
support but includes gaps: treating its full length as a contiguous coherent
integration time would be incorrect. Multiple candidate ranks from one source
window are alternative hypotheses using the same IQ, not independent repeats.

[Position preparation](../../src/leo/application/regional_position_inputs.py)
selects the highest original passing margin per window and projects only the
reduced observation fields into B7. A future uncertainty audit can join original
window/candidate identities back through public projected metadata without
changing persisted contracts or constructing private storage paths. It must
verify those identities and the unchanged top-one selection.

## Cheapest useful diagnostic before any weighting model

An orbit-blind **repeatability screen** can be built from persisted CFO/time/RF
and exact source-support metadata, without satellite labels or TLE predictions.
Keep receiver, channel, edge and exact actual RF fixed. Use nonoverlapping source
sample supports and short measured gaps; never join across RF hops or assume
unobserved continuity. Freeze these rules before examining residuals.

For three neighboring support centers `t0<t1<t2`, let
`w0=(t2-t1)/(t2-t0)` and `w2=(t1-t0)/(t2-t0)`. The innovation
`e = y1 - w0*y0 - w2*y2` cancels a locally affine CFO path. Under the additional
assumptions of equal, independent measurement noise and negligible path curvature,
`e/sqrt(1+w0²+w2²)` has the individual frequency-noise standard deviation. For
equal spacing this is equivalent to the second difference divided by√6.

Those assumptions are **not established** by available fields. The innovation
also contains curvature, oscillator variation, spectral-component switching,
alias changes and selection effects. Its spread is initially a repeatability
diagnostic, not a calibrated variance or CRLB. Overlapping triples share errors;
choose nonoverlapping groups or account for dependence. Cross-receiver frequency
differences additionally contain relative clocks/path effects, so they are not
direct independent repeat observations of one estimator.

Stratify descriptively by sample rate, receiver, actual support geometry and
predeclared margin bins. Do not assign a variance using margin merely because
these quantities correlate in-sample. Orbit-blind Hough grouping still depends
on measured CFO; a held-out CFO used to build its own track has leaked into the
predictive test. Either condition the diagnostic explicitly on frozen grouping,
or construct training groups without the held-out measurement. Do not call it
unseen validation.

The lowest-risk progression is:

1. Verify metadata availability, exact support nonoverlap and repeatability-group
   coverage through public inputs, retaining all members and failures.
2. Test whether a small number of frozen quality/support strata predict repeatability
   on randomized whole-recording/dependency groups, keeping both receivers together.
   Separate interpolation/model error from noise as far as the evidence permits.
3. Only if useful predictive evidence survives, specify a globally frozen bounded
   variance rule and exact uniform-width control. A normalized Gaussian/clutter
   likelihood must retain each row's width-dependent density normalization.
   Match c=0/fitted-c windows, banks, priors, starts and budgets, and report position
   separately from frequency fit. These consumed datasets are not new validation.

A stronger estimator-precision study could remeasure disjoint raw-IQ supports
inside the same physical signal interval. That requires a separately specified,
bounded existing-recording replay and analysis of shared acquisition/detection
selection. It is not available merely by relabelling alternate GLRT candidates
as repeat measurements, and it is not part of this audit. No new RF is needed.

## Earlier results that constrain interpretation

- [Iteration17](../2026_10_08_position_error_iter17/README.md) rejected inverse-count
  density weights:107-member fitted mean1.004952→1.012704/1.025073 km, with worse
  tails. Measurement precision would be a different mechanism, but counting rows
  or renormalizing track density is not an uncertainty calibration.
- [Iteration87](../2026_10_09_position_error_iter87/RESULTS.md) reported margin and
  temporal residual associations as descriptive only. Fitted/assignment-selected
  residuals are not an independent frequency-noise measurement.
- [Iteration106](../2026_10_09_position_error_iter106/RESULTS.md) changed global
  width125→100 Hz: fitted pooled median0.8637→0.8050 km, but the frozen mean and
  regression gates failed. Width sensitivity warrants careful uncertainty work;
  it does not establish a universal100 Hz noise scale or authorize another width
  search against the same failures.
- [Iteration90](../2026_10_09_position_error_iter90/RESULTS.md) showed substantial
  apparent paired bias is confounded with existing clock directions. Repeatability
  statistics must not automatically be labelled LNB noise or satellite error.

The concrete outcome is an input-availability finding: enough public timing,
frequency, detector and support metadata exists to propose a cheap orbit-blind
screen, but **no calibrated per-window frequency uncertainty or SNR is supplied
by the current positioning input contract**. Additional measurements or predictive
validation are needed before a new precision-weighted position model is justified.
