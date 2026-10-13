# Position and satellite timing are strongly coupled locally

The prescribed two-state diagnostic confirms strong position/timing coupling in
the existing DS21-039 model. Allowing satellite timing to adjust, in addition to
receiver calibration, reduces the weakest position curvature by roughly 140×
at the original solution and 300× at the refined solution. This is a local model
property, not a measured position-accuracy improvement or proof of a timing bug.

Both saved fitted-c states passed the finite-difference validity checks. The
run used exactly 418 original marginalized gradient evaluations, zero optimizer
calls and no reference coordinates. It completed in 35.549 seconds overall,
including preparation; the diagnostic runner took 11.051 seconds.

| Saved all-band state | Position curvature eigenvalues after calibration alone | After calibration and timing | Weak-direction prior contribution |
| --- | ---: | ---: | ---: |
| Original winner | 1272 / 3574 | 9.071–9.073 / 70.380–70.381 | About 0.4% |
| Seven-call refined winner | 1971 / 6359 | 6.541–6.716 / 48.062–48.083 | About 0.6–0.7% |

Curvature units are objective units per km², in the existing east/north chart.
Ranges retain both prespecified finite-difference steps. The weak directions
can rotate when nuisance parameters are allowed to adjust; the ratios compare
the smallest eigenvalues, not a fixed geographical axis. Responsibilities were
re-marginalized at every evaluation, so this calculation includes changes in
satellite/native-branch assignments rather than holding them fixed.

## What this explains, and what it does not

Moving the receiver changes predicted Doppler curves. Shifting each satellite's
ephemeris query can compensate for much of that change. Consequently, a fit
that treats timing as known sees much stronger position constraints than the
actual model with fitted timing. This helps explain why combining observations
does not automatically stabilize the position estimate.

However, the large absolute timing prior cost is **not** dominating the remaining
weak-axis curvature. Projecting the exact saved prior Hessian along the fully
profiled weak direction gives prior curvature 0.03377 versus likelihood curvature
9.0376–9.0388 at the original state, and prior 0.04186–0.04440 versus likelihood
6.4966–6.6745 at the refined state. The absolute relative-timing penalties remain
202.405 and 155.244, respectively. Cost at a state and curvature along a direction
answer different questions.

This result does not establish that the timing prior should be tightened, that
the fitted shifts measure actual orbital errors, or that timing freedom alone
causes the position bias. It also does not turn inverse curvature into a calibrated
confidence interval. Satellite association, local minima and model discrepancy
remain relevant; the original and refined positions were not changed by this audit.

## Numerical limits and verification

Full and nuisance Hessians were positive definite under the prespecified scaled
threshold. Maximum full-Hessian relative symmetry error was 3.161e-6. Full-Hessian
two-step stability ratios were 1.828e-7 and 1.107e-5. The fully profiled position
Schur ratios were 2.044e-5 and 0.003640, below the fixed 0.01 threshold.

The refined weakest eigenvalue nevertheless varies by about 2.6% between steps;
the aggregate matrix norm is less sensitive to this small eigenmode. Individual
satellite compensation estimates are less stable still: examples include NORAD
48019 (0.1157 → 0.0507 s/km), 57677 (0.0523 → -0.00033 s/km) and
63850 (0.0783 → 0.1059 s/km), for each step's weak-axis convention. Do not interpret
these as precise physical timing corrections. Some perturbed native queries lie
near the 0.25-second interpolation knots; the report retains those counts and
both step results. Neither endpoint touches a physical constraint.

Saved objective and NLL replay differences were exactly zero; prior closure
differences were below 3.4e-12. An independent audit verified all 336 live/archive
source pairs, six immediate ancestor bindings, historical cold/refinement source
subsets, original attempt/seed bindings, both endpoint seals and the final ten-file
seal. No held observation or reference position was used. The 13 owned tests
passed, and integration passed all 15 component/runner/recipe tests in 1.52 seconds.
Tests include an actual tiny native objective that distinguishes marginalized
curvature from a fixed-posterior calculation, exact quadratic Schur checks,
invalid/weak mode rejection, budgets, failure receipts and cached seals.

Implementation commits: `396064c5e` and `de66132bb`. The
[prespecified protocol](TIMING_CURVATURE_PROTOCOL.md) fixes the steps, scales,
thresholds and budgets. The [independent compact audit](TIMING_CURVATURE_AUDIT.json)
retains matrix summaries, projected prior/likelihood contributions and all
per-satellite compensation ranges. Local evidence namespace:
`reports/2026_10_13_ds21_039_root_cause/local/timing-curvature-v1`.

- Freeze: `sha256:dc6ec6a7285d1405f8172fba882f944daa90d45973d6e67e7e77e858334ae04a`.
- Terminal: `sha256:398f16541bc416769954213b9c85f4afc0db49ae4d20945fc5c57c83d93ee7da`.
- Final seal: `sha256:077668c601d77c7b0c3db407b056c76b6df57c3948408a2787628d3591027486`.

The next prescribed check evaluates the unchanged objective at ±1 km along each
saved compensated weak direction, at both endpoints and both existing steps:
eight calls, no fitting or reference access. It tests whether the local quadratic
description survives a finite displacement before any constrained fit is proposed.
The 0.5 km target remains unmet; this diagnostic does not supply a new prior
setting or an accuracy claim.
