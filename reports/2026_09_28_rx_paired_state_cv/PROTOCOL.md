# Four-state receiver response: calibration leave-one-record-out protocol

Use only the original six calibration recordings and all their qualified exact RF
lane windows. Each fold fits the other five recordings' reception windows, then
scores both periods of the omitted recording. Physically exclude all later and
omitted-record rows before fitting background, normalizers or parameters. This is
development evidence on a reused calibration cohort, not blind confirmation.

## Outcome and model

The observed category is `bool(RX0 candidates) + 2*bool(RX1 candidates)`, giving
neither, RX0 only, RX1 only, or both. Do not read frequencies, margins, ranks or
candidate identities to construct outcomes or covariates. Duplicate entries in a
nonempty receiver set cannot change this response. Qualified empty sets remain
observations; malformed or missing receiver views fail validation.

The training background is one pooled four-category distribution with 0.5 added
to every category. An explicit reset HMM has absent, each retained track/catalog
nominee, and the original omitted-catalog branch. Preserve original candidate
prior mass, including the omitted branch. Absent, omitted and invisible nominee
states emit the background. Occupancy is a latent model parameter, not measured
satellite presence. Track hypotheses are alternatives, not independent signals.

For a visible nominee, define common log odds c, differential log odds d and
shared coupling k. The four unnormalized log probabilities are
`[0, c-d, c+d, 2*c+k]`; normalize all four together. Coupling permits paired
reception dependence rather than assuming independent receivers.

- P: c and d each have intercept, log(sample rate/5 MHz), elapsed seconds/60;
  k is one shared intercept. Seven coefficients.
- U: P plus centered/scaled LOS up and q squared in c. Nine coefficients.
- O: U plus centered/scaled signed q in d, with nonnegative slope. Ten coefficients.

Here q = 2 sin(10 degrees) times LOS east. Compute raw up, q squared and q,
subtract per-lane/per-nominee reception forecast means, and carry those offsets
into later windows. Shared RMS scales are computed on the five training
reception sets only; replace scales below 1e-12 with one. Time starts at each
lane's first reception window. O at zero odd slope equals U; U at zero geometry
slopes equals P. Known scheduled forecast covariates may define omitted-record
centering, but detector outcomes may not.

## Fitting

Gaussian coefficient priors: SD2 for common/differential intercept and coupling,
SD1 for rate/time coefficients, SD0.5 for geometry. Beta bounds ±8, except odd
slope [0,8]. Occupancy-logit prior SD2 and bounds ±7; log-persistence prior SD1.5,
persistence 0.1–10 seconds. Use two L-BFGS-B starts per arm: neutral zeros and
the selected nested parent, with initial occupancy logit0 and log-persistence0.
P's two starts are identical. Limits: 100 iterations, 2000 function evaluations.
Select the converged maximum penalized gain versus training background, or exact
occupancy-zero null if no converged positive gain exists. Fail if no start
converges, rather than treating an unfinished optimization as a scientific null.

## Endpoints and controls

Primary O−U later predictive log score per window, normalized per recording then
averaged equally across six recordings. Also report P/U/O versus background,
U−P, O−P, all six record signs and reception results separately. HMM scoring is
sequential: score each response before updating state weights; earlier omitted-
record responses may condition later predictions but never refit parameters.

Freeze O coefficients for three controls: negate signed q (receiver convention
swap); reverse signed q within each role; cyclically permute signed q among
nominees within each lane. Only signed q changes. Keep unsigned up/q squared,
observations, time/rate terms, priors, visibility and background fixed. These are
controls of the signed feature, not complete physical trajectory replacements.
Require exact null/nesting, normalized emissions, omitted-state accounting,
score-before-update, frequency independence and duplicate-invariance tests.

A gain is a receiver-response result until candidate specificity and an
independently scored frequency/identity bridge are demonstrated. This experiment
does not use frequency-conditioned identity weights. Do not claim improved
satellite association from generic detection prediction or a shared pass trend.
Do not select the swapped convention after seeing results. Physical mapping and
world tilt remain provisional; no decoded satellite identity truth exists here.

## Execution

Bound each fold to 120 seconds, one numerical thread and 4 GiB. Freeze protocol,
source, tests, launcher and input hashes before running. Preserve every failed
attempt and optimizer receipt. No RF collection, IQ reprocessing, new propagation,
QNAP mutation or evaluation/DS8 scoring. Independently audit training isolation,
preprocessing, optimizer objectives and per-window score aggregates before any
promotion decision.
