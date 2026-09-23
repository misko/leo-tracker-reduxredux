# Conditional full-eight-hour shared per-scan epoch fit

Use exactly the 72 sessions in the frozen Sep 21 00Z TRAIN group and require the
sealed blind baseline's session order to match that cohort exactly. Freeze every
track identity separately for each Sacramento/Reno baseline arm. This is a
conditional fixed-identity ablation, not full blind reassociation.

Fit one altitude-zero geographic position and one epoch effect per scan, shared
by all tracks in that scan. Do not add a per-satellite effect. Each track retains
a constant CFO profiled on training rows. Bound scan effects to ±5 seconds and
position to the corresponding original 250/500 km prior disk.

Run all Gaussian-shaped regularization scales 0.2, 1.0, and 5.0 seconds with the
same objective as the accepted first-six nuisance experiments: duration-weighted
capped-800-Hz track loss plus `800^2 * sum((tau/scale)^2)`, divided by total
duration before square root. Scales are regularization settings, not calibrated
clock uncertainties.

Apply the accepted deterministic solver uniformly to all six arms: at most five
block iterations of bounded scalar scan updates and 2D Powell position updates,
then at most 50 bound-active Schur Gauss–Newton polish iterations. Use ±0.1 km
position and ±0.01 s timing derivatives, freeze outward directions at active
bounds, recompute the free system, and backtrack on the exact capped objective.
Record scalar work, steps, stopping rule, pre-step projected-gradient diagnostic,
visibility failures, and timing boundaries.

Fit and seal all arms using training rows only before opening complementary rows
or reference coordinates. Report exact tau-zero baseline parity and every scale
and prior without geographic selection. No validation/test, prospective evidence,
deployment, or RF collection is included.
