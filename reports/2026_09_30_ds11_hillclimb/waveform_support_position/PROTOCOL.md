# Prospective nominal temporal-support sensitivity

Use the previously frozen scan-0 measurements, both pilot arms, and all111
target training observations. Compare against the existing original IID and
unchanged-timestamp pilot fits. No new IQ, later orbit data, source selection,
measurement filtering, or reference-dependent model choice is permitted.

For each corrected training observation, evaluate every candidate's unchanged
causal orbit bank at the original observation time plus the nominal pilot-minus-
GLRT support-center difference recorded by the support audit. Reuse the original
piecewise-linear state interpolation at each observation. Keep measurement
values, RF aliases, nuisance offsets, likelihood scale, all other rows, and all
localization-held timestamps and values unchanged. This tests geometric support
centers; amplitude-weighted frequency sensitivity is not established.

Preserve the original four starts per arm. Eight atomic90-second fit attempts,
at most three workers, one BLAS thread each, nice19, no recovery or retries.
Restrict the timing search to[-4.995,4.995]seconds solely to keep shifted queries
inside the original[-5,5]second bank; existing compared endpoints are interior.
Apply the existing endpoint gradient and finite-difference qualification.
Choose each arm's highest qualified training score and seal both selections
before geographic scoring. Report every failed attempt. No geographic comparison
unless both arms have a qualified endpoint. No model promotion follows this
single exposed-scan sensitivity, regardless of error change.

The relevant question is whether the long-arm reference error remains below
the original IID control after nominal support alignment, and how much it moves
from the existing751.262m result. The shorter arm is retained as a control.
Compare original-model and changed-training predictive held scores separately;
held measurements still use the original GLRT estimator. Do not call this a
uniform waveform re-estimation or an estimate of actual estimator time weights.
