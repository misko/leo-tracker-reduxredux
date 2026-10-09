# Next model hypotheses after B7

This memo proposes research; it implements no model and reports no new fit.
The review read existing consumed-development reports and source, plus newer
recording membership/exposure metadata. It did not inspect reserve localization
outcomes, collect RF, or change production. The three mechanisms below were not
evaluated in the reviewed iteration1–85 localization sequence; this is not an
exhaustive novelty claim about every earlier repository experiment.

The [completed B7 ablation](../2026_10_09_position_error_iter85/DECISION.md)
has fitted-c mean1.317354km across148 recordings. Descriptively removing its
single53.400741km error leaves approximately0.963km across147 recordings.
That calculation is not a proposed exclusion or replacement benchmark. It
shows why catastrophic-case recovery alone cannot meet the0.4km goal.

## Mandatory first step: audit residuals under B7

Before any prototype fit, reconstruct all148 accepted B7 endpoints in both
c arms and reproduce their stored objectives. Retain all63 DS16,51 DS17 and34
DS18 members, with explicit input failures. Produce a uniform per-recording
audit of simultaneous receiver differences, within-track temporal correlation,
association confidence, and available measurement-quality evidence. Known
coordinates/errors are evaluation-only and must not define groups, eligibility,
weights, hypotheses, or operational winners.

The evidence motivating these hypotheses predates B7. Its receiver clock,
RF-time and satellite-slope stages may already remove the patterns. Historical
selected-case diagnostics are neither evidence of current prevalence nor
proof of physical cause. Freeze the audit rules before reading new residual
summaries; report every member rather than only conspicuous examples.

## 1. Regularized receiver-by-satellite frequency contrast

This is the first priority if the B7 audit confirms persistent paired offsets.
[Iteration23](../2026_10_08_position_error_iter23/README.md) reports these
RX1-minus-RX0 residual differences after its then-current receiver corrections:

| Consumed diagnostic group | Simultaneous pairs | Mean difference Hz |
|---|---:|---:|
| FRESH-003 /60366 |46|−32.10|
| FRESH-005 /63383 |55|−25.22|
| FRESH-006 /57772 |12|−24.33|

The same report shows why unpaired means are misleading: an apparent178Hz
difference had zero simultaneous pairs. Its
[residuals.py](../2026_10_08_position_error_iter23/residuals.py) joins the same
inferred satellite/channel and timestamps rounded to milliseconds, averaging
duplicate observations within each receiver before differencing. Reuse and
qualify that definition; do not substitute nearest-time pairs silently.

### Proposed model and identifiable parameterization

For observation i, receiver r and candidate satellite k, add
`z_r * d_k / 2` to the B7 frequency prediction, with `z_0 = -1`, `z_1 = +1`.
Thus d_k is the full RX1-minus-RX0 differential in Hz, not a per-receiver offset.
Over the K eligible satellites, use `d = U theta`, where U has K−1 orthonormal
columns perpendicular to the all-ones vector. This enforces `sum(d) = 0`,
removing the receiver-wide contrast already represented by receiver clocks.

Use three globally fixed research hypotheses: Gaussian prior scales
**10,30,60Hz**, with penalty `theta.T @ theta / (2*sigma**2)`.
These are proposed widths, not validated hardware distributions, and must not
be selected separately for each scan. Coefficients initialize at zero.
Include an exact zero-variance control that removes or locks all contrast
coefficients, plus a same-start B7 refit to identify computation effects.
The prior is a soft restriction. Any inherited numerical coefficient bounds
must be documented and checked for activity.

Zero-sum removes a gauge; it does **not** establish data identifiability when
receiver coverage differs or contrasts resemble other nuisance corrections.
As a predeclared guard, freeze eligibility from ordinary B7 responsibilities
above0.5 with at least10 same-channel, rounded-ms receiver pairs per satellite.
Apply the same eligible set to both c arms. Set corrections to zero for other
satellites; fewer than two eligible satellites makes this extension an exact
no-op. Keep all observations and candidate satellites in the likelihood.
This fitted-derived eligibility makes the c comparison conditional and must
be disclosed. It is a hypothesis to test, not a proven optimal threshold.
Report eligible counts and weak-information cases rather than claiming that
the guard guarantees identifiability.

### Physical interpretation and limits

A receiver LO offset is shared across satellites; the proposed interaction is
not another receiver-wide clock coefficient. Polarization alone does not
establish a carrier-frequency offset. Different spectral components selected
by the receivers, channel effects, association errors, or measurement bias
could produce the observed contrast. The old evidence does not distinguish
these mechanisms or establish an LNB fault. If the B7 audit supports channel
or spectral-component identity as the simpler explanation, prefer that
explanation to assigning a physical satellite error.

The rule transfers without geographic constants: it depends on simultaneous
measurements and inferred assignments, not the reference position or fixed
satellite IDs. Every recording starts with zero contrasts and the same prior.
This does not establish worldwide, different-hardware, or mobile performance.
Flexible contrasts can still absorb position information, just as flexible
satellite slopes can; apparent fit improvement is not sufficient evidence.

### Implementation hook and component tests

Prototype an isolated extension of
[SatelliteCorrection](../../src/leo/analysis/hard60_satellite_correction.py)
and [SlopePrior](../../src/leo/analysis/hard60_slope_prior.py), inserting its
coefficient block before the final two RF-time coefficients. The contrast
gradient is the eligible-satellite projection of
`sum_i(prediction_gradient[i,k] * z_receiver[i] / 2)` through U.
Keep B7 timing, receiver clocks, RF-time and common satellite-slope terms fixed
as model definitions; optimize their coefficients jointly as before.

Required tests cover exact zero-variance nesting, finite-difference gradients,
receiver-exchange sign symmetry, satellite permutation and basis-rotation
invariance, zero-sum contrasts, unchanged RF locks, and no-op cases with sparse
or absent paired support. Synthetic identifiable data must recover injected
contrasts; deliberately weak-information data must not be presented as uniquely
identified. A receiver-wide shift should remain represented by existing clock
terms rather than the new zero-sum mode.

Report paired residual changes, contrast sizes, position shifts and their
relationship to RF/slope changes. Audit whether new assignments recruit
observations to exploit extra freedom, a failure already observed with overly
flexible [satellite slopes](../2026_10_08_position_error_iter25/README.md).

## 2. A temporally correlated residual likelihood

[Iteration16](../2026_10_08_position_error_iter16/README.md) measured substantial
adjacent residual correlations, including0.34–0.68, with sampling gaps around
0.42–0.89seconds in selected groups. The later
[inverse-count weighting experiment](../2026_10_08_position_error_iter17/README.md)
failed; it did not test a calibrated covariance model.

If correlation remains under B7, prototype a time-gap-aware OU residual process
within orbit-blind receiver/channel tracklets, with proper innovation variance
and normalization. Preserve clutter and uncertain satellite assignments rather
than hard-assigning every observation or merely differencing neighboring
residuals. Zero correlated variance must exactly reproduce B7.

The hook is a research adapter around
[hard60_score.likelihood](../../src/leo/analysis/hard60_score.py), using the
existing orbit-blind track membership. This is a larger change than contrast
offsets: the current likelihood is a product of independent per-window
mixtures. Correlated mixture evaluation needs explicit marginalization or a
clearly documented, separately qualified approximation. First measure
out-of-block residual predictability; do not infer a covariance model merely
from pooled descriptive correlation or normalize weights by track counts.

## 3. Measurement-quality-dependent frequency uncertainty

The current likelihood uses one scalar frequency sigma.
[PositionObservations](../../src/leo/contracts/regional_position.py) retains
per-window margin, and
[prepare_position_windows](../../src/leo/application/regional_position_inputs.py)
selects the highest original GLRT-margin candidate in each window. Margin does
not currently supply a per-observation variance in that likelihood.

Test whether orbit-blind measurement repeatability predicts useful uncertainty,
then consider a frozen variance vector
`sigma_i**2 = sigma_floor**2 + measurement_variance_i` with bounded widths,
the Gaussian normalization retained, and the existing clutter mixture. Include
the exact uniform-width control. Margin is not established SNR or calibrated
variance; do not invent a margin-to-variance map without measurement evidence.

This differs from rejected density weighting because it models measurement
precision rather than the number of observations in a bin. A research
likelihood adapter can accept the frozen vector without changing published
contracts. Any raw-IQ remeasurement would be a separate input experiment,
using existing recordings only; it must not be mixed into a claimed model-only
comparison. No remeasurement or RF collection is performed by this memo.

## What is already explored

[Iteration84](../2026_10_09_position_error_iter84/README.md) already proposes
geometry-protected satellite-slope priors; it is not a new hypothesis here.
[Iteration83](../2026_10_09_position_error_iter83/README.md) covers ordinary
clock continuation and regional recovery. Receiver-wide differential RF
stretch was tested in
[iteration2](../2026_10_08_position_error_iter02/README.md) with negligible
benefit; that is distinct from the satellite interaction proposed above.
None of these prior experiments should be relabeled as new work.

## Evaluation before any operational promotion

Use all148 consumed DS16/17/18 recordings, retaining full membership, failures
and prescribed fallbacks. Freeze randomized whole-recording groups, enlarged
where duplicate or shared-input dependencies require it; keep both receivers
together. Stratify by dataset and sample rate where group counts permit.
Never split individual windows between training and validation. Existing-data
folds assess development stability, not fresh independence after repeated
inspection of this corpus.

Calibrate any learned uncertainty/correlation rules on training groups only.
Freeze one global model choice and acceptance protocol before inspecting an
audited newer reserve. Keep observations, banks, eligibility, starts, other
priors and budgets matched between c0/fitted-c. In c0, static c and RF-time
terms remain locked; receiver-by-satellite contrasts remain available in both
arms because they are not RF-stretch coefficients. Disclose fitted-derived
shared starts and eligibility as a conditional c ablation.

Include a same-start B7 refit control and independent convergence checks.
Never compare raw objectives across changed likelihoods/priors to choose an
operational winner. Reference errors enter only after inference. Report
per-dataset and pooled mean/median/p95/worst, paired regressions, convergence,
fallbacks, input failures, and full exposure membership; frequency-fit effects
remain separate from position accuracy. No per-scan best-error selection,
reference-guided seeds, satellite lists, or region retention is permitted.

## DS18+ metadata and exposure authorities

The [iteration75 reserve report](../2026_10_09_position_error_iter75/README.md)
and [membership receipt](../2026_10_09_position_error_iter75/membership.json)
describe11 existing recordings in
`[2026-10-08T23:08:51Z,2026-10-09T02:02:21Z)`.
Local authority is
`/home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter75/local/manifest.json`,
with `seal.json` beside it. Its manifest SHA256 is
`71e7477408e31449c14f85a7ae87155780e88c2503dc06544ab00a59016483af`.
The original audit found no filename exposure in its audited scope; that is
not proof of unseen validation. Re-audit exposure metadata before opening
outcomes. Keep both receivers and every member, and record missing inputs
instead of substituting recordings. This memo leaves its outcomes closed.

The first ordinary B7 deployment completion is already explicitly consumed:
`scan-fw-7ebf76971ca06c00`, recorded in the
[deployment exposure receipt](../2026_10_09_hard60_b7_rollout/live-exposure.json),
with input digest
`sha256:e9d7e040f61072c4ead63efb0ae33b4e15b06e47df3102d8e3e08f14ffb3d4cb`.
It was selected by first ordinary completion, not reference error, but its
outcomes have been inspected and cannot be called unseen validation.

No additional authoritative minted post-DS18 development cohort was located
in this review. Any extension should begin with metadata-only membership and
exposure auditing before outcome access. Do not infer independence from an
unmatched filename, and do not reclassify previously consumed
NEW/FRESH/LATER/RESERVED recordings as fresh validation.
