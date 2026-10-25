# DS24 new-family orbital uncertainty: bounded mechanism test

Status: approved for preparation on 2026-10-25. No fits are authorized until
the input, construction and numerical audit below passes. This is a new version;
the movement-policy r01 and preceding sources/results remain immutable.

## Question and scope

Does removing unsupported orbital-shape coordinates make a newly recovered
one-owner family an excessively certain position constraint? The existing
support control removes three coordinates from both the fitted mean and the
marginal covariance. Removing uncertainty is different from declining to
estimate a correction. This is a plausible mechanism, not established physical
orbit error or satellite identity ground truth.

Use only the two already studied fast scans and the exact sealed additions:
DS24-0095 / NORAD65500 / 49 RX1 CH5 points and DS24-0087 / NORAD57752 /
43 RX2 CH7 points. These are previously examined development examples selected
for mechanism diagnosis, not an unseen validation sample. No search for more
favorable families, point trimming, raw IQ, post-scan TLE, or new RF collection.

## Models and ownership

Retain the original saved baseline curved and predictive observations,
identities, aliases, receiver/orbit/fragment priors and calibration ownership.
The new source is a separate predictive factor; it must not update the original
curved calibration or noise learner. A predictive factor can affect position.
The two new branches differ ONLY in the new source's orbital-shape covariance:

1. `predictive_shape_zero`: new family's three shape modes have zero variance.
2. `predictive_shape_prior`: use the existing declared physical three-mode
   prior, at its original scale, as uncertainty in the target prediction.

Both use the same original causal phase mean/variance, unseen-noise convention,
source constant prior and original shared calibration covariance. Preserve
joint covariance with the original predictive entries: do not independently
score factors that share receiver uncertainty. Include the complete quadratic,
log-determinant and normalization terms. No hand-tuned variance inflation,
new RX1 correction or altered receiver-noise law.

Explicitly distinguish target local uncertainty from information already in
the parent. Avoid double-counting a dormant parent-family phase or shape prior.
Freeze target phase linearization from causal inputs without fitting that phase
from target observations. Document the Gaussian approximation and any physical
linearization error; a wide phase prior may limit interpretation. This pilot
does not establish that a calibrated orbital correction is supported by one
owner, and does not bypass the original graph support rule.

Saved controls are baseline, ordinary full-shape graph trial and phase-only
support trial. Preserve the ordinary graph trial's INVALID support status.
The new predictive branches change evidence role relative to those controls;
only their mutual comparison isolates shape covariance.

## Wave 0 before fits

SOL B owns implementation, proposal/input freeze and all new scientific outputs.
SOL A independently checks the covariance algebra and construction tests.
SOL C audits original contracts, objective consistency, ownership, budgets and
later geographic reporting. Coordinator reviews readiness and fixes the cap.

- Pin exact parent and target IDs, input/result/source hashes, candidate index,
  time/RF/CFO/alias/sigma values and TLE epoch/collection cutoffs.
- Show deleted physical prior projections at fixed saved endpoints; these are
  engineering-prior diagnostics, not measured errors or calibrated intervals.
- Check the actual frozen parent optimizer residual scalar against the reported
  objective at saved endpoints and fixed offsets, accounting for constant noise
  normalization and visibility penalties. No assertion of a baseline solver bug.
- Independently reproduce joint predictive scores using dense Gaussian algebra
  on actual target/parent-predictive vectors. Test zero-shape equivalence,
  shared-covariance cross terms, PSD, target redaction and duplicate prevention.
- Changing target CFO must leave fixed-position parent calibration, phase
  references and Gamma precision unchanged. Target receiver/channel/RF and mode
  units must retain original bindings. Both c arms must have identical IDs.
- Compare phase-linearized target prediction against direct propagated Doppler
  at fixed prior offsets. Report deviations before interpreting Gaussian gains.
  Do not repair failures by tuning phase variance to geographic results.
- Tests must own the new adapter; no golden-fixture or production edits.

## Fixed diagnostics and bounded propagation

After the independent preflight and coordinator go receipt:

- Fixed-position path: 11 equally spaced positions between each scan's saved
  baseline and phase-only-support endpoints, separately for each c arm. Both
  predictive branches use every same position, ID and prior. At most 88 total
  branch/position evaluations. Report target conditional innovation, score
  decomposition, curvature after nuisance projection and parent objective.
  These segments are diagnostic profiles, not a global minimum search.
- At most EIGHT new position fits: two scans × two covariance branches × two
  c arms. Ordinary cold regional start [0,0], original 25×25 km region centered
  37.906, -122.545, five phase rounds × 48 position iterations. No multistart,
  constrained rescue, new identity or retry of statistical failures.
- Two numerical workers maximum, one BLAS/OMP/MKL thread each; 180 seconds per
  arm and 20 minutes total from first scientific propagation. A timeout remains
  visible and retains the baseline; no automatic extension.
- Every original parent ID and all original parent residual/visibility gates
  remain protected. Evaluate target residual structure with the declared
  predictive uncertainty and report exact semantics. Record unsupported or
  uncalibrated quantities explicitly. No existing gate is quietly redefined.
- Freeze all RF results/decisions before adding geographic evaluation. Known
  GPS is reporter-only; the development cases have prior geographic exposure.

Both c=0 and fitted-c retain matched observations, candidates, other priors,
starts and budgets. Frequency score, association compatibility, likelihood
membership, conditional information and position error are separate outputs.
Do not label all target likelihood inputs as accepted satellite associations.
If a new factor is not qualified, report its endpoint as diagnostic, never as
an adopted improvement. Do not select a branch per scan using geographic error.

## Deliverables and stopping rule

Publish an MD iteration report with: prior uncertainty projections, the complete
saved-control table including invalid support status, the fixed-position score
profiles, residual/CFO figures, all eight attempted fits and gate outcomes,
matched c-arm geographic comparisons, source/input seals and independent audit.
Use the standing isolated publication workflow; preserve unrelated root changes.

No ALGO release or immediate full-cohort expansion. If the covariance difference
does not explain the 0095 contrast, close this hypothesis and move to the next
diagnostic. If it does, separately freeze a general policy that distinguishes
association, prior uncertainty and calibrated orbital modes, then test a broader
chronologically/ID-defined fast cohort including regressions and controls.
Do not generalize two known scans or target a 90% association quota.

Conditional followups remain separate: extending existing conditional synthetic
tests to fast geometries/selection effects, and direct simultaneous same-family
RX contrasts using native CFO. Neither requires a new radio campaign, and neither
is claimed as already validated by this pilot.
