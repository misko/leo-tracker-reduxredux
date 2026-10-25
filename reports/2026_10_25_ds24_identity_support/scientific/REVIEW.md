# Review and proposed bounded identity-support check

This is a review-first proposal. No new simulator, numerical campaign, position
fit, RF collection or operational identity assignment has run. Original studies
and their unqualified outcomes remain unchanged. The fast-scan improvement goal
is still open.

## What the immediate repair would establish

The previous conditional nomination test produced eight ordinary-shortlist
physical truths out of eight, all coarse rank1 and all raw exact rank1, in both
c arms. Only seven physical orderings qualified. The eighth was blocked because
a *different* candidate, 100539, crossed below the horizon somewhere in the
phase domain; the winning truth 56530 passed its quadrature. All four polynomial
null draws favored the null in raw score, but none qualified. Some required
runner-up physical scores are roughly 400,000–4,400,000 objective units above
the null. The maximum reported dense/adaptive discrepancy is about 0.0136,
and nine adaptive guards failed. These are unresolved ordering checks, not
evidence that the raw winner was wrong. Source:
[original findings](../../ds24-nomination-information-r01/nomination/FINDINGS.md).

The strongest reason **not to prioritize this as a localization intervention**
is that it changes neither the already successful ordinary shortlist nor a
position model. It may turn large-gap, easy conditional comparisons into
qualified arithmetic. It cannot authenticate the inherited real identities,
resolve the real close competitors or demonstrate improved locations. It is
useful enabling work only if followed by a harder, correctly conditioned
identity test. The latest parent-uncertainty experiment also failed conservative
residual gates despite phase/Gamma convergence; its failures were not these
identity-integration guards.

## Minimal separately versioned change

1. **Visibility is phase support, not an all-domain veto.** For a complete
   source, set its physical likelihood to zero whenever any retained native
   observation is geometrically below the horizon. Integrate over the remaining
   phase intervals with the *unchanged* Student location, scale, nu and original
   normalization on [-15,+15] s. Never divide by visible prior mass or redraw an
   invisible realization. Save visible prior mass and the zero-likelihood mass.
   Empty certified support means exactly zero physical evidence; unresolved
   support is a technical abstention. Out-of-bank propagation remains a failure.
   This explicitly changes the physical visibility/event model; it is not just
   a numerical repair. Its integral is a joint CFO-plus-visibility-event density,
   not a CFO density renormalized after conditioning on visibility. It does not
   supply a calibrated detection or null-occurrence probability.

2. **Enumerate support from the actual interpolation rule.**
   `paired_phase_states` uses linear bank states followed by Earth rotation.
   Partition each observation's phase at bank_knots minus its timestamp. On
   each piece, visibility has the sign of
   `h(phi)=up·[Rz(omega*phi)(a+b*phi)−observer]`.
   A valid second-derivative bound is
   `|h''|<=2|omega| norm(b_xy)+omega² max norm(a_xy+b_xy*phi)`.
   Midpoint Taylor bounds certify positive/negative pieces; derivative bounds
   certify monotonic pieces with at most one bracketed root. Subdivide uncertain
   pieces under a frozen depth/evaluation cap and intersect the observation
   supports. This handles interpolation discontinuities, narrow intervals and
   tangencies without treating a dense grid as a proof. Any remaining uncertain
   interval stays unresolved, rather than silently discarded. Final root and
   support-boundary accuracy must be checked against the score error budget.

3. **Avoid extreme-density cancellation and underflow.** Keep the original
   covariance, physical modes, priors and uniform finite aliases -4,…,+4.
   Replace the subtractive Woodbury quadratic by its equivalent positive form
   `norm(w−Bwhite*alpha)²+norm(alpha)²`, with
   `alpha=(I+Bwhite'Bwhite)^−1 Bwhite'w`. Use log-domain integration and log-sum
   accumulation over certified visible/interpolation pieces. Local SciPy 1.18.1
   exposes `tanhsinh(log=True)`, so no new integration framework is required.
   Proposed primary rule: relative target 1e−9, zero absolute target, frozen
   refinement cap, with reported log error and termination status. Its internal
   error estimate is not itself an independent or rigorous certificate.
   Preserve the determinant term alongside the stable quadratic. Independently
   replay required competitors using composite Gauss-Legendre on the same
   physical pieces with two predeclared orders. Bound phase batches to avoid
   large vectorized-bank allocations. Final node/refinement orders must be
   chosen on analytic tests before real regression values are read.

The **absolute 1e−3 objective agreement requirement stays unchanged**. Translate
integral error into a −2 log evidence error, rather than accepting an absolute
integral tolerance that is large relative to a tiny integral. Require independent
agreement and finite positive error evidence for the winner and every relevant
competitor. Choose that set from the denser ranking and ordering-uncertainty
overlap, preserving the old top-two rule. Do not exempt an improbable loser,
replace a failed winner, backfill a true label or widen the shortlist/alias prior.
Independently inspect log-scaled narrow-mode tests and endpoint behavior; two
agreeing finite grids alone do not certify that every mode was found.

## Proposed owned tests and bounded replay

Before freezing a runner, test: all-visible equality to the old normalized
density; a constant likelihood times visible prior mass; exact zero on empty
support; disconnected and very narrow visible intervals; a tangent/uncertain
support that abstains; piecewise interpolation roots against direct geometry;
stable positive quadratic against dense covariance, including huge residuals;
an analytic narrow Gaussian mixture with log integral near −1,000,000;
separated/endpoint modes; finite alias normalization; and unchanged shortlist
misses/no truth fields at the observation port. Tests must report false
convergence, not simply produce finite answers.

First replay the **same 12 archived observations**, both c arms, from their
sealed source-specific cavity mean/covariance and ordinary eight-candidate
shortlists. Reconstruct/hash-check those inputs; do not regenerate the draws or
relearn a parent. Preserve old scores beside the new support law, every failed
guard and the complete 12-trial denominator. Separate visibility-law changes
from numerical changes on all-visible cases. Cap the complete proposed branch
at 600 scientific seconds, two workers, one BLAS thread each, and no position
fits/retries. Root/B approval and a frozen protocol are prerequisites. A budget
or convergence failure is a valid stopping result.

A possible *later predeclared* four-draw matching-law control would use one
physical and one polynomial-null draw per existing layout, with a target
Gaussian background frozen before CFO and identical in generation, screen and
exact score. This is an exogenous-background, target-specific-orbit experiment;
it is not a fully shared-family parent simulation when alternatives had old
parent evidence. Only c0 is the matching generating arm; fitted-c remains a
same-data sensitivity arm. The original two-stage full-parent-generator versus
shortlist-cavity scorer remains a separate diagnostic. Fresh identities/seeds,
law and inclusion in the 600-second cap require explicit protocol discussion
before any draw. No fresh controls are authorized by this note. See the
[independent conditioning review](../review/REVIEW.md).

Stop after the regression check if actual comparisons still fail the unchanged
error requirements, support cannot be certified within cap, or the only gain is
turning already obvious null gaps into qualified arithmetic. That would justify
reporting a numerical limitation, not extending the campaign.

## Three opportunities, ranked independently

1. **Test genuinely confusable identities under a matching conditional law.**
   The eight successful new truths were all ordinary rank1; they did not stress
   the real 0011/0012 close competitors. Freeze confusable pairs by predicted
   curve geometry and metadata before new CFO; use the ordinary catalogue port,
   equal candidate treatment, an explicit unresolved alternative and a frozen
   conditional background. Compare ordinary and known-label controls on exactly
   the same observations and conditional law, differing only in label
   availability; otherwise conditioning changes confound the interpretation.
   A small falsification test can distinguish an easy
   catalogue demonstration from useful identity evidence. Stop if the known
   truth is frequently absent/unresolved or if an alleged corroborating owner
   was selected by its response/label. Any later held-owner evidence must be
   metadata-selected and retain shared radio/orbit covariance; the existing
   same-RX1, same-label witnesses are not independent identity validation.
   The 0013 eight-candidate/null and three whole-owner conditional comparisons
   have already run and favor 60108. Repeating those same owners would not be
   a new test; first establish availability of a witness selected independently
   of that historical label, ideally from the other receiver.

2. **Separate phase/shape identifiability from inference approximation with one
   coherent nonlinear reference.** Noiseless known-label fast controls recover
   within 0.8–2.5 m, while declared noisy draws reach 1.09 km and still pass the
   original gates. Removing generating phase alone changes mean fitted-c error
   from 0.4689 to 0.4026 km; removing shape alone gives 0.4054 km; removing both
   gives 0.2966 km. This supports coupled nuisance ambiguity, not phase-only
   dominance or an optimizer defect. The distinct next check is one fixed
   synthetic realization under identical labels, priors, noise and observations,
   comparing the existing ACTIVE-PARENT calibration approximation with a direct
   nonlinear phase/physical-mode reference for the same conditional model.
   Predictive-target and identity kernels already evaluate physical B(phi) at
   every nonlinear phase node; repeating those integrals is not new work.
   Begin with fixed-state score/gradient closure
   and computational feasibility, not another multi-start/oracle factorial.
   If the reference cannot match the modeled law or barely changes the result,
   stop attributing that draw's error to the approximation. Sources:
   [fast controls](../../ds24-fast-identifiability-r01/README.md),
   [factorial](../../ds24-phase-shape-validation-r01/synthetic/FINDINGS.md).

3. **Check measurement/selection consistency on a tiny verified fixture.**
   Every recent conditional simulator fixes inherited source masks and native
   measurements; none reproduces GLRT peak selection or its conditional noise.
   A waveform/known-pilot fixture through the actual fast CFO selection path
   would test that missing layer. First identify a valid existing estimator
   port and verified signal/pilot model; compare pre/post-selection frequency
   bias and declared uncertainty, with failures retained. This is different
   from merely lowering CFO scatter. Stop at the prerequisite if no verified
   fixture exists, and do not start a broad IQ campaign. The previous 322-curve
   RX2 remeasurement lowered median scatter 78.07→22.18 Hz without a qualified
   localization gain; a repeat precision campaign has weak priority. Existing
   reports support only a targeted selection/bias question, not a claim that
   CFO bias caused these location errors.

Generic continuous restarts already returned within 2.06 cm in 30 targeted
fits. The all24 held-family movement policy retained three corrections, only
one geographically beneficial. Later RX1 validation improved fitted-c mean by
15.4 m, with three improvements, three regressions and two fallbacks, and
worsened the tail. The new retained-parent covariance control changed local
information but admitted zero of four candidates. Common-family rankings,
same-label witnesses, higher coverage, cleaner in-sample residuals and tighter
unsupported priors therefore remain weak stand-alone selectors. None of the
three opportunities above justifies operational adoption or a new ALGO series
before bounded evidence establishes broader benefit.
