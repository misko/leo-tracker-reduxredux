# Parent orbit uncertainty in current fast-scan inference

Started 2026-10-25 19:48 UTC. Previous goal turn: **progress**. It published
commit 79f8bc300848c930e1a2879f8e268362cd97f232, completed ordinary catalogue
nomination and information-ranking controls, and identified 33/89 active
scan-family instances lacking physical orbit modes in DS24-0010–0013. Those
families contribute 1,544/12,442 position-likelihood IDs. No operational
improvement was established; the fast-scan goal remains active.

## One mechanism, reused implementation

Retain the existing causal three-mode physical prior for active parent families
currently omitted solely by the RX/channel support rule. Existing DSX01
all-candidate uncertainty experiments already tested the mechanism with mixed
outcomes; this is a current fast-pipeline comparison, not a novel universal fix.
Use the same four chronological exposed development cases, all original curved
and predictive points, aliases, identities, powers, other priors and c arms.
No new sources, nominees, source trimming, collection or GPS-dependent choices.

SOL xhigh A owns implementation, tests, fixed-state diagnostics and a prepared
matched fit runner under `scientific`. SOL xhigh B owns independent mathematical
and gate review under `audit`. SOL xhigh C reviews prior art and support
semantics, evaluates sealed outcomes and publishes the final report. Root
coordinates the scientific decision and synthesis. Use apply_patch; preserve
unrelated root changes (tracked diff SHA256
add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b).

## Uncertainty versus qualified calibration

The existing `p.supported` field controls both physical feature columns and
acceptance-owner checks. Blindly expanding it changes the gates; hiding newly
fitted physical means from the owner predicate would admit unsupported orbit
corrections. Therefore declare two sets explicitly:

- The likelihood integrates the original shared three-mode prior for every
  active family, preserving full curved/predictive covariance.
- Original calibration support remains frozen for a conservative gate view.
  That view omits all new prior-only physical posterior means from orbital
  profile predictions, curved conditional residuals, predictive residuals and
  postfit extensions. It retains original residual/alias/visibility thresholds
  and the original support cascade. No predictive observation calibrates radio
  or orbit coefficients.
- Also report the literal expanded-mode/full-mean legacy gates separately,
  including their newly activated owner vetoes. Do not choose the better gate
  interpretation after seeing geography or silently relabel a correction.

This is an explicit research adapter. It does not authenticate any identity or
promote a mode estimate to a measured orbit correction. The existing reference
remains operational throughout this four-case study. A hypothetical research
candidate/fallback policy can use only predeclared paired conservative
qualification and original ownership requirements, never geography. Raw fit
outcomes remain visible even when unqualified.

## Bounded execution and transition

First freeze the implementation/protocol and obtain B's mathematical preflight.
Test zero extra variance against the unchanged baseline; preserve coefficient
layout, prior normalization, shared predictive covariance and the separation
of prediction from calibration. Compare fixed-state objective components and
central gradients at each saved endpoint and ±0.01 km axes, with a second step
for derivative stability. Inspect local mean-design information, clearly
separated from actual nonlinear objective curvature and calibrated confidence.
For the primary information control, freeze the OLD mean Jacobian, observation
weights, phase/noise precisions and mean coefficients; append only the new
shared physical design with its unit Gaussian prior. This isolates omitted
covariance and must not increase information. Information recomputed with the
candidate's refitted precisions/mean can be supplementary, but cannot silently
replace this primary control.

The fit-stage triage is declared before results: proceed with all four matched
cases if at least one case has both c arms showing either (a) predicted movement
of at least 50 m from −0.5 I_baseline^-1 times the change in negative-twice-ELBO
gradient, or (b) at least 5% change in the original weak-direction local
variance. These are engineering work-allocation thresholds, not acceptance
criteria, geographic selection or a claim of actual movement. A numerically
blocked pair remains blocked, with no replacement case.

If warranted, run at most 16 position fits: four cases × two c arms × unchanged
cold baseline / retained-uncertainty candidate. Use the same [0,0] regional
start, five phase rounds and 48 iterations per round in the existing 25×25 km
box centered at 37.906,-122.545. The scientific branch has 600 seconds total,
at most two workers/one BLAS thread each and 120 seconds per case. No retries,
rescues, broader priors, increased budgets or alternate starts for unfavorable
results. Retain all terminal failures and raw checkpoints.

Seal RF outputs before geographic evaluation. Evaluation uses only the already
declared site 37.849061591561885,-122.48574968092912. Compare frequency score,
gate decisions, all native ownership, actual likelihood and postfit membership,
position distribution and runtime separately. Both c arms share observations,
candidates, other priors and search budgets. These four cases are development
data, not a fresh holdout. No ALGO promotion without broader verified benefit.

Publish an MD report, figures, code/tests, failures and replay requirements to
remote main under the standing iteration-report authorization. No production
contracts or golden fixtures change; QNAP remains read-only. No new RF campaign,
stationary pooling, future-TLE inference or moving-trajectory prototype.
