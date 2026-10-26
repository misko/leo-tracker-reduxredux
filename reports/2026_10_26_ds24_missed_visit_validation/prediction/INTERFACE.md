# Timing/validator interface: constant-epoch primary v2

Read predictions.json.rows[*]; example_packet.json is fabricated with no IQ.
All rows bind exactly the original primary branch through primary_hypothesis_id
and donors. Header and target_support retain integer native generation,
stream label, full support and source digests. No-donor rows have empty methods.
Fallback rows contain both control and unchanged fallback point with reasons.

methods.linear is the consistent constant-epoch linear control.
methods.quadratic_or_fallback is the single proposed point.
methods.legacy_adapter_linear reproduces the round1 adapter's extra rate*0.010.
Every method's epoch_samples is relative to target origin and is the constant
epoch to pass to the scorer. Do not add another rate*midpoint offset. The
explicit legacy_adapter_minus_consistent_linear_epoch_samples discloses that
difference. Do not count the legacy descriptive control as an extra automatic
acceptance opportunity.

Each historical whole-window constant-epoch measurement is assigned NOMINAL
MIDPOINT-EFFECTIVE timing phase, not an exact instantaneous origin phase. The
scoring point is evaluated at target midpoint and expressed relative to target
origin. Model/origin/end evaluations and reference counters remain explicit.
Unequal pilot weighting can invalidate this approximation. This does not
silently change or reproduce round1 raw scoring: its legacy adapter point is
reported separately. Independent validation of this convention is required.

cfo_hz, cfo_rate_hz_s, cfo_reference_counter, reference_offset_s and frequency
uncertainty are copied from round1's original primary full prediction for all
methods. Timing adjustment neither creates an independent frequency likelihood
nor improves the443.9Hz profile grid's precision by itself. The timing owner
owns raw scoring and the validator owns frequency/grid-origin qualification.

Model timing coefficients use normalized u=(relative_seconds−center)/scale;
phase=beta0+beta1*u+beta2*u². Its reference is the latest donor midpoint;
epoch_reference_base_samples is relative to that donor's origin. For any
reference, evaluate phase and subtract target_origin−donor_origin modulo
sample_rate/750. predictor.evaluate implements this plus engineering variance.
Propagate rates as derivatives of the same scaled polynomial. No model values
are chosen from the target's samples, original winner, geography or truth.

Root interpretation caveat: round1's 30 new natural admissions mostly use one
or two donors; only three use at least five and only fourteen select primary.
This primary quadratic is a bounded computation/mechanism comparison, not an
expected replacement for sparse multimode timing search. No hybrid scoring is
introduced here.
