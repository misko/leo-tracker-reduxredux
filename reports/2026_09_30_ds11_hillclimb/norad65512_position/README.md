# Direct DS11 waveform corrections: small scan-0 reference-error gain

The longer known-pilot correction reduces scan0's error against the existing
unsurveyed roof reference from765.072m to751.262m: **13.810m**. The shorter
correction worsens it to773.810m. Both arms and all eight optimizer starts are
retained. This is a single exposed-scan mechanism test, not a validated DS11
policy or proof of general positioning improvement.

A subsequent [nominal temporal-support audit](support_audit.json) identifies
an unresolved comparison detail: the eight-frame long pilot's geometric center
is typically4.279ms earlier than the preserved GLRT timestamp, which summarizes
more frames. At the cached control and conditional NORAD65512, the corresponding
model frequency difference has medians13.308Hz and13.148Hz on the two tracks.
After removing each track's median, its RMS is only0.802Hz and0.707Hz, versus
33.247Hz and22.952Hz for the measured long corrections. This suggests that the
nominal timing effect is mostly a track offset; it neither proves that the
13.810m gain is an artifact nor establishes that the gain survives matched
measurement timing. Actual amplitude-dependent estimator weighting is not
measured. No IQ is reread and no position is refitted in this audit. The original
experiment and its frozen sources remain intact; a prospective support-aware
comparison is required before interpreting replication as estimator improvement.

That [prospective nominal-support comparison](../waveform_support_position/README.md)
is now complete: long745.342m and short767.233m, with all eight starts qualified
and no conditional MAP identity changes. The long-arm gain survives this
nominal timing check; actual effective estimator weights remain unmeasured.

| Measurement input | Qualified starts | Reference error | Change from control | EN displacement from control |
|---|---:|---:|---:|---:|
|Original cached IID control|Previously qualified, exact replay|765.072m|—|—|
|Short pilot, symbols2–65|4/4|773.810m|+8.737m|66.760m|
|Long pilot, symbols22–221|4/4|751.262m|-13.810m|24.083m|

The [measurement audit](../norad65512_waveform/RESULTS.md) supplies all111 direct
training-frequency corrections for each arm. No weak result is removed or
smoothed, and neither arm is selected from waveform-held scores. Original
aliases, timestamps, causal orbit states, candidate mixtures, likelihood scale,
CFO profiling, masks and all65 localization-held values in the target tracks
are unchanged. Other tracks' measurements are unchanged as well.

Each arm uses the original IID initializer plus three generic starts. Highest
qualified training score chooses its endpoint; [selections.json](selections.json)
is written before geographic scoring. All eight starts qualify and all processes
exit0. The largest within-arm EN disagreement across starts is0.00049m for the
short arm and0.00604m for the long arm. This demonstrates numerical consistency
of these starts, not a global-optimum certificate.

| Held-score change from original control,nats | Short | Long |
|---|---:|---:|
|Unchanged original IID measurement model at new point|+0.201142|+0.011226|
|Corrected-training IID model, unchanged held observations|-4.287079|-0.160170|

The longer correction's modest geographic gain is not accompanied by an
improvement in corrected-training predictive score on localization-held points.
Those points retain their original GLRT measurements; this mixed measurement
comparison must not be described as testing uniformly re-estimated held data.

The separate [conditional association audit](association_audit.json) changes
zero of62 MAP NORAD assignments in either arm. Both corrected tracks remain
conditionally assigned to NORAD65512, with row mass rounding to1.0. This is not
an authenticated identity. Under the long correction, training RMS residuals
at the final conditional candidates change122.049→115.262Hz at11.21GHz and
136.470→136.912Hz at10.71GHz. Substantial residual mismatch remains.

The position movement from long corrections is small compared with the earlier
kilometre-scale source-deletion sensitivity. The result provides a concrete
measurement-derived gain on this recording, but does not support treating
these two tracks' fractional-frequency estimation errors as the explanation
for that much larger sensitivity. It does not rule out larger gains on other
tracks or scans, better measurement timing, or different association models.

## Verification and evidence

Preparation replays the original control score and gradient exactly and passes
fresh finite-difference qualification. It completes in2.51seconds. The eight
fits take6.01–11.52seconds each and25.31seconds wall time at most three workers,
with one BLAS thread and a90-second cap per start. No retry or recovery occurs.
Nine patch/selection tests and two association tests pass. Independent
pre-execution review verifies all63 source bindings and the complete protocol.
Independent post-execution review rehashes the plan and outcome sources,
verifies all eight receipts and training-score selections, and reproduces the
three geographic errors and both held-score comparisons without discrepancy.

The frozen plan SHA256 is
`a3f5e925cc9cdf508074ec8e3527b7fcdc604ae63aeb82fd1db03e19eddd5f43`.
[outcome.json](outcome.json), all eight per-start results and receipts in
`runs/`, and the preparation/batch receipts preserve the evidence. The broader
improvement goal remains open; no production model or golden fixture changes.
