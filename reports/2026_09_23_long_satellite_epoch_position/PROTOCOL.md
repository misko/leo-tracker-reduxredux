# Conditional per-satellite epoch position fit

Use exactly frozen long-cohort TRAIN[:6]. For each Sacramento/Reno arm, freeze
every track identity to the corresponding sealed blind tau-zero baseline. This
is a conditional identity ablation, not full blind reassociation and not a claim
that fitted effects are physical orbit corrections.

Fit one altitude-zero position and one epoch effect `eta` per selected satellite,
shared by all of that satellite's tracks within and between the six scans. There
is no per-scan epoch term. Each track retains a constant CFO profiled on training
rows. Bound position to its original prior disk and every eta to `[-5,+5]` s.

Run all regularization scales 0.2, 1.0, and 5.0 seconds with objective
duration-weighted capped-800-Hz track loss plus
`800^2 * sum((eta/scale)^2)`, divided by total duration before square root. These
are Gaussian-shaped regularization scales, not calibrated uncertainties.

Avoid dense numerical differentiation over all satellite parameters. Starting
from the sealed baseline position and zero etas, run at most five deterministic
block iterations. At fixed position, update every satellite independently with
bounded scalar minimization (`xatol=0.002 s`, at most 40 evaluations), retaining
the prior value if it is better. Then update only east/north position with bounded
Powell (`maxfev=100`, `xtol=0.02 km`) while holding etas fixed. Retain the best
penalized training state and stop when an iteration improves the objective by
less than 0.01 Hz. Report convergence, iteration trace, eta bounds, exact
visibility failures, and the number of non-negligible eta effects.

Then polish every arm with at most 50 coupled Schur Gauss–Newton iterations.
Numerically differentiate CFO-centered training residuals at ±0.1 km in each
position direction and ±0.01 s in the owning satellite eta. Weight each row by
track duration divided by its training-row count, omit currently capped tracks,
and eliminate satellite steps through the diagonal nuisance block before solving
the 2-by-2 position system. Backtrack each step against the exact original
capped penalized objective, clip eta to ±5 s, and reject prior-disk or visibility
violations. Stop below 0.01 km and 0.002 s step or 0.001 Hz objective gain.

Revision before the accepted run: the first coupled implementation clipped eta
after an unconstrained Schur solve. Review showed active bounds require freezing
outward eta directions and recomputing the position/free-eta system. The
unprojected source and output are preserved separately; the revised active-set
rule was applied uniformly to all six accepted arms. Projected-gradient values
are recorded before each attempted step, so the last value is a last pre-step
diagnostic rather than a post-fit KKT certificate.

Fit all six arms using training rows only. Seal positions, etas, identities,
offsets, and traces before complementary-row or reference scoring. Report exact
tau-zero fixed-identity baseline parity and all arms without geographic
selection. No long validation/test, prospective evidence, deployment, or RF
collection is included.
