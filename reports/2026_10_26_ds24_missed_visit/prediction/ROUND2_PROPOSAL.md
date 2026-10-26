# Proposed second-round primary quadratic point forecast

Status: **proposal only; not implemented, not run, not approved for dependent
RF/validation evaluation**. The round1 predictor, protocol, forecasts and
outcomes remain immutable. The root decides whether round1 evidence justifies
this as the second and final bounded prototype. No target-tuned timing bias
subtraction or physically fixed RF coupling is proposed.

Use the same frozen panel, earlier donor histories, candidate/rank policies,
branch associations and primary mode ordering. Fit only that retained primary
history. Keep its existing linear CFO forecast and all native ownership. Do not
choose a branch or model by a target response, score, known signal or position.

Use an independently fitted quadratic timing-phase trajectory only when all
conditions hold:

- At least five distinct earlier donor visits span at least 1.0 second.
- Center and scale time before fitting; the quadratic design has rank three
  and condition number at most 100. Use QR/lstsq, never an unscaled explicit
  polynomial inverse.
- Fitted timing acceleration magnitude is at most 10 samples/s², and the
  propagated timing-rate magnitude is at most 200 samples/s.
- All donor ownership/causality and existing original-rank rules remain valid.

When any condition fails, retain the sealed linear timing or one-donor fallback
with its broad uncertainty. A cell without a donor remains unavailable. Preserve a reason for
every fallback. The thresholds are the exact conservative proposal discussed
with the coordinator, not thresholds selected by target outcomes.

Timing covariance uses residual variance with at least a 0.75-sample noise
floor, n−3 residual degrees of freedom and forecast leverage at the target
origin; add a fixed two-sample model-discrepancy floor in quadrature. Preserve
coefficient covariance, acceleration uncertainty, support span, condition number
and fallback reasons. All intervals remain engineering scales without physical
RF calibration. Do not turn narrow prior uncertainty into extra observation
weight. Source packet and code must be frozen before any second-round outcome.

Predict epoch at the full 20ms target origin and CFO at its nominal midpoint,
then evaluate **one unchanged full-window conditioned GLRT score**. This avoids
a new target timing search and the half-window power penalty. Preserve the
constant-epoch within-window approximation and nominal CFO-reference caveat.
It does not prove that a profiled CFO bin is an independent precise Doppler
measurement: compare raw likelihood/grid-origin behavior separately and retain
donor conditioning as prior information. Original-binned and carry controls use
the identical target samples and original branch. No extra mode trials or
outcome-selected alternatives are admitted.

Motivation is donor-only curvature: 347/362 selected primary histories have
negative curvature, with an implied extrapolation offset close to the observed
systematic timing error. The leave-last-donor diagnosis excludes that donor
from coefficients but not historical membership selection; it is not independent
qualification. The apparent positive RF-scaled coupling is not used because
RF/LO/IQ/clock sign conventions remain unresolved. Target recovery, null/search
exposure, frequency accuracy and matched c-arm position effects require their
own frozen qualification rules. A higher GLRT or lower training residual alone
cannot promote this method.
