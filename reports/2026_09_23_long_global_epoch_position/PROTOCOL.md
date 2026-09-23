# Conditional global epoch position fit across nested TRAIN durations

Use frozen TRAIN[:6], TRAIN[:16], and the full 72-scan Sep 21 00Z TRAIN group.
For each view and Sacramento/Reno arm, freeze track identities from its sealed
blind tau-zero baseline. Require exact ordered session membership and cache
bindings. This is conditional fixed-identity inference, not reassociation.

Fit one altitude-zero position and one global epoch term shared across every
track and scan in a view. Each track retains a constant CFO profiled on training
rows. Bound global tau to ±5 seconds and position to the original prior disk.
There is no per-scan or per-satellite epoch term.

Run regularization scales 0.2, 1.0, and 5.0 seconds using duration-weighted
capped-800-Hz track loss plus `800^2 * (tau/scale)^2`, divided by total duration
before square root. These scales are not calibrated clock uncertainties.

For all 18 arms, start from the corresponding sealed tau-zero position and zero
tau. Run at most five block iterations: bounded scalar tau minimization
(`xatol=0.002 s`, 40 evaluations) followed by bounded 2D Powell position update
(`maxfev=100`, `xtol=0.02 km`). Then run at most 50 accepted-source bound-active
Schur Gauss–Newton polish iterations using ±0.1 km position and ±0.01 s tau
derivatives with exact capped-objective backtracking. Stop below 0.001 Hz gain or
jointly below 0.01 km and 0.002 s step. Record raw last pre-step projected
gradient, work, steps, bounds, visibility, and stopping rule without claiming
KKT certification.

Fit and seal all 18 arms using training masks before computing complementary-row
or reference metrics. Report exact zero-tau parity and all scales/priors/views;
do not choose by geographic outcome. The hypothesis tests whether a simpler
common shift preserves more position information across duration. It cannot
establish a physical receiver clock offset. No validation/test, prospective
evidence, deployment, or RF collection is included.
