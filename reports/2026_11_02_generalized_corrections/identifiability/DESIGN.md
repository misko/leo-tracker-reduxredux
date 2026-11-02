# C: other-family RF displacement support

This diagnostic asks whether a saved candidate's position displacement survives
recalibration using **other satellite families**, after allowing their shared
hardware, receiver/band offsets, drift, smooth calibration, fitted-c (in that
arm), phase, physical orbit and fragment constants to explain the data jointly.
It never requires the target on both receivers or a majority of points.

The scope is the identical fixed curved native observation set. Conditional
entries and phase-mixture observations are counted but excluded. Both c arms
must be run separately on matched inputs. No GPS, case-specific condition,
NORAD-specific rule, candidate fitted coefficient, or saved phase reference is
used. Geometry uses the declared zero absolute-phase reference and causal
phase prior mean. Nominal phase linearization remains an approximation.

At the control and candidate position, build the two nominal prediction vectors
and the complete nuisance design. On the other-family rows, form one nuisance
space from the union of both endpoint designs. Project the observed CFO,
nominal endpoint difference and control residual against that space. With fixed
150 Hz noise, let `s` be the projected standardized endpoint difference and `r`
the projected standardized control residual. Report displacement information
`s.T@s` and RF support `2*r.T@s - s.T@s`. This is exactly the residual-quadratic
improvement in a common linear nuisance span. All nuisance coefficients are
unrestricted, so the primary diagnostic has no prior penalty or covariance
volume that can masquerade as residual support.

Every leave-one-other-family-out calculation constructs its own nuisance space
and fits hardware using only its retained rows. It does not reuse a full-data
hardware estimate. Family deletion tests robustness, not independence: different
families can share hardware and orbit error not represented by this model.

The following engineering gates were fixed before cohort outcomes: at least
three other families, full displacement information >=4 and RF support >=4,
and every leave-one-family-out calculation retains information >=1 and RF
support >=0. These numbers are **not calibrated significance levels or a
two-sigma statement**. SVD normalizes nonzero columns before a relative 1e-10
rank cutoff. Empty residual space and effectively zero signatures are explicit
abstentions. No prior-regularized sensitivity can rescue a rejection.

A separate normalized fixed150 Gaussian sensitivity integrates nominal nuisance
priors at SD multipliers .5, 1 and 2. It reports the residual/prior quadratic and
log determinant separately, plus posterior standardized coefficient norm. The
inherited fragment SD is .3. Gamma precision posteriors and heavy-tailed phase
priors are not used, so this is an engineering Gaussian diagnostic, not the
inference model's exact marginal likelihood. Its ordering cannot change C.

The union projection is deliberately conservative. It can project away real
position information, especially when short orbit arcs resemble phase/orbit
error, and therefore may abstain almost everywhere. Abstention does not show a
bad association. A pass is also not a guarantee of improved localization:
positions were selected using the same RF, fixed identities and masks remain
conditional inputs, white-noise scatter is not calibrated, and shared unmodeled
errors may remain. Independent position evaluation belongs to the root only
after RF decisions have been sealed.

The report-local API is `evaluate_guard(base_context, candidate_context,
control_endpoint, candidate_endpoint, arm=..., target_family=..., z=...)` in
`guard.py`. It uses saved positions without position optimization and returns
the decision, continuous support, confounding, rank, deletion and prior
sensitivity diagnostics. Synthetic tests cover joint recalibration, confounded
motion, candidate-only nuisance, single-family dominance, opposing RF, full
span and subset recalibration.
