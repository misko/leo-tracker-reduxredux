# Cheap search recovery for embedded analysis

The next design should spend computation on distinct geometric hypotheses, then
solve receiver nuisance parameters with small structured algebra. Iteration83 is
a useful exhaustive development control, not a suitable embedded implementation.
No proposed approximation below has been fitted or has measured position accuracy.
Production B7 and the frozen, currently running83 experiment remain unchanged.

## Measured cost and source evidence

Read-only snapshot at **2026-10-09T15:35:01Z**:83 workers232285/232301 were running
under serial runners232284/232300. DS16-043 had336 immutable clock-fit receipts,
295 qualified, totaling2627.04 fit-seconds; its35 regional attempts added267.63s.
DS16-050 had241 fits,207 qualified, totaling2561.24 fit-seconds;35 regions added
328.10s. Loading, census construction, receiver-pair proposal generation and other
overhead are excluded from these sums. These partial results do not establish
candidate position error or a search stopping rule. Receipts are append-only while
workers run, so counts are a timestamped snapshot, not terminal totals.

The two common banks have118/147 satellites and60/62 feasible source identities.
Each source can request five initial states (original plus two pair proposals with
two receiver anchors), each in both arms, then up to four cross-arm continuation
fits: at most14 fits/source. Up to eight shared complete-state restart fits follow.
Thus these inventories permit up to848/876 clock fits, each bounded at90s and600
iterations. The time bound is not a prediction: observed attempts generally stop
earlier. Enumeration multiplies dimension, hypothesis count and optimizer overhead.

Evidence hooks:

- [83 evaluator](../2026_10_09_position_error_iter83/evaluate.py): enumeration,
  continuation, immutable fits and independent qualification.
- [83 engine](../2026_10_09_position_error_iter83/engine.py): common final-bank
  union, nuisance-preserving transport, visibility/physical checks and hard bounds.
- [83 policy](../2026_10_09_position_error_iter83/policy.py): timing trigger,
  regional retention and score-only qualified selection.
- [Clock proposals](../2026_10_09_position_error_iter67/clock_starts.py) and
  [circular consensus](../2026_10_08_position_error_iter36/consensus.py): exact
  millisecond/RF singleton pairing and241 slope-grid proposals per invocation.
- [Joint clock model](../../src/leo/analysis/hard60_joint_clock.py) and
  [dynamic RF model](../../src/leo/analysis/hard60_dynamic_rf.py): linear clock
  designs, Gaussian precision, affine-null clock basis and independent convergence.
- [Likelihood](../../src/leo/analysis/hard60_score.py): clutter plus circular
  satellite mixture. Its nuisance optimum is not an unconditional least-squares solve.

## Three replacements to prototype

### 1. Profile the linear clocks instead of optimizing their coordinates jointly

Keep geometry/timing as the outer variables. At a fixed hypothesis, freeze mixture
responsibilities and circular winding choices. Solve a regularized weighted linear
subproblem for receiver affine terms, clock coefficients and optional RF terms:

`(Xᵀ W X + P) β = Xᵀ W (y − g)`.

Use a QR/Cholesky factorization with rank checks, honoring hard60 and other bounds
through a small active-set solve. Preserve the clock null basis so affine clocks
are identifiable. Do not clip a solved vector and claim constrained optimality.
Recompute the exact mixture objective; accept only a feasible decreasing step and
refresh assignments/windings. Two or three deterministic inner rounds give a
bounded approximation; an exact conditional solver remains a development control.

This removes many clock variables from the expensive outer SLSQP problem and avoids
repeating both receiver anchors: a unique fully solved conditional clock block is
anchor-independent. Uniqueness is not guaranteed for the circular mixture; retain
multiple winding/proposal hypotheses when supported. The weighted linear solve is
exact only for its fixed-assignment surrogate, not for the complete likelihood.

For embedded memory, stream row contributions into small normal equations and keep
a rank-revealing reference QR implementation for qualification. Every spatial region
still receives its own conditional solve and exact common-model score.

### 2. Search the two geometry directions after eliminating nuisance directions

At each retained region, form local spatial Doppler derivatives and the linear
nuisance design. Project spatial derivatives through the weighted nuisance
complement, or equivalently use the Schur complement of the nuisance block.
The resulting2×2 information matrix identifies strong and weak horizontal search
directions. Take a bounded Gauss-Newton step with a small deterministic backtracking
set, re-evaluating orbital geometry, visibility and the exact score after every
accepted step. Limit iterations and distance explicitly; maintain the original
region representative alongside its refined state.

If the projected matrix is poorly conditioned, refine along the weak direction
with a short symmetric line grid rather than forcing a misleading Newton step.
Use a rank cutoff frozen globally, never a receiver-reference coordinate. Small
low-rank timing directions can be added only when supported by the Jacobian;
discarding many satellite timing modes changes the model and needs its own ablation.

This offers predictable small-matrix work and geometric interpretation. Visibility
boundaries, changed assignments and circular wrap transitions can invalidate local
linearization; exact score checks and retained alternate regions are essential.
The projected matrix describes local information and does not prove global accuracy.

### 3. Deterministic breadth-first screening and bounded refinement

Screen every distinct retained region cheaply under the **same observation set,
bank, priors and parameterization**, using one or two profiled-clock rounds. Preserve
one representative per region; no global top-K deletion before every region is
evaluated. Deduplicate clock proposals in predicted nuisance-frequency space, not
by geographic proximity alone. Analytic conditional solves should make the two
anchor variants redundant when they lead to the same feasible clock prediction.

Spend the next fixed batch on regions with promising comparable scores, uncertain
screening approximations or unqualified fits. Expand one child in every unresolved
region before spending a second refinement in the current best region. A deterministic
queue can combine exact score improvement, local curvature/conditioning and boundary
contact, with stable region indices for ties. Avoid calling surrogate gaps statistical
confidence or treating them as rigorous lower bounds without a proof.

Stop at a frozen operation budget, reporting unresolved regions and qualification
failures. Require independent stationarity before accepting an optimizer result;
one score-selected complete-state restart may receive a reserved budget. Original
B7 fallback remains explicit when a candidate is unavailable; its score is not
compared against a changed-bank/model recovery objective. Timing strain, residual
pair inconsistency, boundary contact and lack of qualification can trigger work;
reference error never can. A trigger is tested for missed failures, not assumed
to detect all poor positions. Reserve inexpensive coverage for untriggered cases.

This changes computation allocation without requiring a large hypothesis solver.
It may lose accuracy at tight budgets; that tradeoff should be measured and exposed.

## Comparability and B7 integration

Use candidate positions only for hypothetical orbital geometry and local Jacobians.
Reference coordinates, distance errors and the earlier diagnostic rescue seed are
excluded from operational bank construction, starts, retention and selection.
Satellite inventories come from the same documented reference-free policy for all
members. Union their final-fit banks before ranking recovery hypotheses; transport
timing/clock states with the existing physical-preservation assertions.

83 is a sigma1 common-bank search atop a slope0.25 research control, without B7's
RF-time and slope0.5 extension. It cannot be spliced into B7. A separate frozen
experiment must feed recovered ordinary hypotheses through one uniform final B7
model and compare qualified candidates on that model. If a shared bank differs
from deployed B7, rerun the B7 control under that shared bank as well. Preserve the
deployed result as a fallback, never score-rank two incompatible models.

## Lean qualification and ablation

1. Test synthetic linear-clock solves, constrained active sets, rank deficiency,
   circular wrap hypotheses and c=0/RF locks. Verify nuisance projection against
   direct block algebra, finite differences and prediction-preserving transports.
2. Replay frozen hypothesis inventories to isolate computation changes. Compare
   joint fitting against profiled clocks first, then add projected geometry, then
   deterministic screening. Include same-start/same-bank full-compute controls and
   equal-budget controls; changing bank, model and search simultaneously hides causes.
3. Evaluate every DS16/17/18 member, including all raw failures and the additional15
   DS16 members. Preserve exposure labels and count unresolved regions. Both c arms
   receive matched observations, inventory, priors and operation budgets; freeze
   any shared fitted-derived assignments before applying the arms and disclose them.
4. Report mean/median/p95/worst error, paired regressions, convergence/fallbacks,
   frequency fit separately, wall time, objective/orbit evaluations, inner solves,
   peak memory and implementation size. Plot error against operations and memory.
   Record embedded target measurements before making speed or power claims.
5. Freeze a globally chosen Pareto tradeoff before randomized independent
   whole-recording validation on newer on-disk data. Do not tune per scan using
   reference error. No new RF collection is requested. Retain a simple variant if
   its measured cost advantage outweighs a disclosed modest accuracy penalty.

Recommendation: prototype **profiled clocks first**, using retained regions and the
unchanged exact likelihood as acceptance checks. It attacks repeated high-dimensional
work while keeping geometry and score meaning visible. Add the2D projected search
and bounded queue only after this algebraic baseline is qualified. Target0.4km remains
unachieved; none of these proposals has a measured localization improvement yet.
