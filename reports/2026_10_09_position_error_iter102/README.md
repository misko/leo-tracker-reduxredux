# Direct bounded qualification of retained calibration failures

The ac11 investigation required several separate causal experiments. They are
not a proposed production retry chain. Test the smallest candidate: one direct
call to immutable iteration100 reduced-Hessian polish from a saved failed fit.

The generic trigger is a retained ordinary region whose calibration prefit or
postfit failed independent qualification. It applies at every grid level; no
reference error, grid spacing, particular coordinate or satellite ID selects a
case. Preserve every original candidate and qualified winner. Do not spend this
budget on arbitrary grid points, accepted fits or a failed association stage.
Any replacement must pass the existing full KKT and physical constraints before
it enters the same ordinary score-based downstream winner policy.

The trigger input `independently_qualified` means the fit's full independent
physical/KKT acceptance, never the optimizer's success flag. Optimizer success
can coexist with failed qualification, as ac11 demonstrates.

One attempt: at most two Newton rounds and100 objective evaluations, initial
128 ULP score allowance, unchanged0.001 KKT, fixed regional position, hard60
bounds and fitted-c shared calibration. No alternative seed, repeated retry,
ridge or threshold change. For tangent dimension d, the first complete central
Hessian sweep and one candidate need at least2d+2 evaluations. If that exceeds
100, record `dimension-exceeds-budget` without evaluating and preserve the
failure. No hidden budget increase or selected subset of coordinates. The solver
may stop sooner for nonpositive curvature, blocked face or unqualified result.

The two-state diagnostic independently starts (1) the original ordinary failed
prefit saved in iteration93 and (2) the corrected failed postfit saved in95.
The latter's model uses the already frozen qualified prefit96, solely to isolate
whether postfit polish needs the97→99 chain. Therefore these two tests do not
by themselves constitute a fresh end-to-end direct calibration pipeline. If both
qualify, a separate same-policy continuation must construct the postfit from
the directly qualified prefit and validate matched c-arm finals and B7.

Input reconstruction verifies the same observations, orbit bank and objective.
Those reconstruction checks are reported separately from the100-evaluation
polish budget. Within `qualify`, score verification is folded into its first
counted objective evaluation. No extra hidden evaluation is used to decide the
generic retry trigger. Every original and candidate state is retained.
Polish wall time and input-reconstruction wall time are recorded separately.
This research diagnostic has an evaluation cap, not a production wall-time
deadline; no embedded latency guarantee is claimed. A deployable policy still
needs a predeclared wall deadline and fallback.

Preparation only until parent freezes/publishes and runs. No production source
change, RF collection, reserve access or position-reference use. Generalization
requires full declared-cohort failure coverage, matched c arms, compute/fallback
counts and paired regressions; a single-case success is insufficient deployment
evidence.
