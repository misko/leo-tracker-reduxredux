# Generalized numerical, orbital-history and identifiability prototypes

This experiment follows the [family uncertainty stress test](../2026_11_02_family_reliability/README.md) and [conditional prediction experiment](../2026_11_02_predictive_reliability/README.md). It implements three general policies on the same available ALGO07 fast-scan roster, without fitting any policy parameter to evaluation position. Every scan receives matched c=0 and fitted-c decisions. Production sources, satellite identities, graph joins, native ownership and association coverage remain unchanged.

## Common comparison

The available roster has 205 unique recordings: DS24 25/34, DS26 148/159, DS27 13/15, DS28 14/16 and all five recent control recordings. The 24 source members without comparable saved outcomes are unavailable, not successful or failed prototype fits. DS25's adaptive cohort is not included or counted again. All recordings use the user-confirmed site only for postdecision geographic evaluation.

The numerical adapter reconstructs each saved ALGO07 RF context. It verifies saved position/objective agreement and the full native union across curved, conditional and mixture observations. Three previously accepted ALGO07 identity repairs remain exactly preserved; the experiment does not reconstruct an older ALGO06 result and label it ALGO07. Two inherited owner-versus-likelihood mismatches are explicit unchanged fallbacks. Every newly fitted candidate must retain the full native union and fitted ownership; incidental extension proposals do not increase reported coverage.

Both c arms and both numerical/prior models start from the same saved fitted-c RF position and phase reference, within the existing 25 × 25 km regional box centered at 37.906, −122.545. These are local refinements of existing inference, not new cold-start localization or catalogue searches. All existing priors and empirical likelihood weights are retained except the declared target-family covariance intervention.

## A: numerical repair with unchanged physical priors

The trigger is raw phase nonclosure above 0.01 seconds or a stable nonzero projected central position gradient above the existing 1e-4 optimizer tolerance. Gradients are checked at 0.001 and 0.01 km steps. The cross-step stability requirement is the greater of 1e-4 or 25% of gradient scale. These tolerances are numerical engineering choices, not statistical confidence levels.

The existing one-sided finite difference produced materially different gradients from central differences at the two previously abnormal DS26-0309 receiver-transfer endpoints. The repair therefore uses half-damped phase-reference updates and, when needed, an explicitly supplied central position Jacobian. It does not add a new orbit parameter, change a phase prior, or choose a satellite. An abnormal optimizer exit or stable nonstationarity after an apparently successful solve can trigger the central-Jacobian rescue. Fixed-reference rescue adoption requires nondegradation.

Both arms must pass optimizer success, raw phase closure, stable final projected central stationarity, finite inner Gamma precision change ≤1e-5, existing physical/residual/exact-orbit/mixture gates, and unchanged ownership. The candidate position must not worsen the objective relative to the saved arm's position when **both positions are evaluated under the same final phase reference**. The difference from the original saved objective is diagnostic only: changing phase reference changes an approximate marginal surface and is not an invariant exact-likelihood comparison.

If either arm fails, A retains the exact saved ALGO07 pair. The old RF score is never combined with GPS to decide whether a repair is accepted. [Solver implementation and measured gradient discrepancy](solver/README.md).

## B: independently constructed causal orbital covariance

The target is the first family nominated by the existing generic RF influence trigger. There are no case-specific or satellite-specific exceptions. The prototype adjusts one nominated family, rather than changing all catalogue priors at once.

The uncertainty value is computed from orbital history only. Both TLE epoch and recorded availability must precede the scan cutoff. Actual TLE satellite numbers, epoch bytes, nominal-file hashes and archive snapshot receipts are checked. Repeated identical snapshots are not independent orbital updates; an earlier collection of identical bytes can witness availability of a later repeated nominal snapshot.

At least three older TLE epochs separated by six hours and spanning twelve hours are required within the previous 72 hours. Each historical orbit is aligned to the nominal orbit using orbital states only, with a ±120 second bound and explicit convergence requirement. The state comparison uses the minimum, midpoint and maximum timestamps of all native observations. Position and velocity are compared after scaling velocity by orbital radius divided by inertial speed; phase-tangent disagreement is removed before projecting into the existing three physical modes: mean motion, inclination and RAAN.

The zero-mean three-coefficient covariance is replaced by an uncentered history second moment shrunk 50% toward identity. Its eigenvalues are bounded to [1,16], retaining the original variance floor and the previous SD×4 ceiling. This is an engineering proxy, not a calibrated orbit covariance or independent-orbit-truth estimate. Historical disagreement reuses information related to the baseline mode scales; it is not counted as independent new evidence. Less than 50% represented state energy, unresolved basis rank, unavailable provenance or failed alignment causes an unchanged fallback. No unsupported residual direction becomes a new free coefficient.

The three mode columns are transformed using the covariance Cholesky factor while the integrated coefficients remain standard normal. This retains the normalized Gaussian determinant and prior penalty. No current-scan CFO residual or GPS value chooses covariance magnitude. The B endpoint uses the same repaired solver, starts, observations and physical gates as A. It is selected only when history is supported and both arms qualify; an improved RF score is **not** an additional acceptance requirement. Otherwise the selected A output is retained. [Covariance implementation, inventory and tests](covariance/README.md).

## C: conservative other-family displacement support

C reuses the B endpoint and asks whether its movement from the selected A endpoint is supported by the other satellites. It does not perform another position optimization. All eligible curved target-family observations are excluded. Ancillary conditional and mixture evidence is omitted from this diagnostic and reported separately.

The two endpoint geometries are built at a declared zero absolute-phase reference with causal prior means. Neither the target-fitted hardware coefficients nor a fitted phase reference is frozen into the test. The union of receiver/band/drift, smooth calibration, phase, orbit and fragment nuisance directions at both endpoints is projected out jointly. Each leave-one-other-family-out comparison recalibrates the retained shared nuisance span.

With a fixed 150 Hz diagnostic scale, C requires projected displacement information ≥4 and RF quadratic improvement ≥4, at least three other families, and every family-deletion counterfactual to retain information ≥1 and nonnegative improvement. Both c arms must pass. These are engineering gates, not calibrated significance thresholds; other families can share unmodeled errors. A separate nominal Gaussian prior sensitivity calculation cannot rescue a rejection.

Allowing the whole nuisance span without prior restrictions can remove real position information. Therefore abstention does not establish a wrong association or a harmful correction. C is deliberately a test of strong data support independent of nuisance regularization. If it rejects every case, that is a lack of useful discrimination, not a successful correction policy. A C failure retains the selected A output, not the accepted B output. [Guard design and limits](identifiability/DESIGN.md).

## Execution and audits

The first numerical run has eight BLAS-one workers and a 1,200-second global ceiling, including case loading. Model-arm cells have a 120-second cap; preparation and each guard arm have 60-second caps. The solver allows fifteen phase rounds, 35 optimizer iterations, 140 legacy objective evaluations, 140 rescue optimizer evaluations and 800 actual objective calls per reference, explicitly counting Jacobian/probe work. Every failure or cap remains a terminal outcome with its completed earlier policy stages preserved.

The first attempted launch was rejected before any workers or fits because the reviewer tightened its postfit audit during source sealing. The unused original protocol is preserved. A prelaunch amendment changes only the reviewer-file hash; all scientific code and policy remain unchanged. The authoritative first execution uses [execution_protocol.json](execution_protocol.json).

Measured RF-only throughput showed that the first window would leave a large unattempted queue. Before any candidate geography was opened, [coverage_protocol.json](coverage_protocol.json) prospectively authorized at most two further 1,200-second waves with sixteen BLAS-one workers. They may run **only cases that were never started**, with unchanged scientific/cell budgets. Any worker elapsed marker, non-manager case artifact, diagnostic, checkpoint or model-arm receipt permanently excludes a retry. All prior workers must be joined and their ledgers sealed. The original run is not extended, and its started/capped cases cannot be replaced.

The final combined ledger must retain exactly one authoritative immutable source row per available scan. It records component hashes and per-case provenance, with no retrospective selection by score or position. Independent audits reconstruct policy decisions and stage fallbacks, check source/input/causal bindings, and replay a bounded set of endpoints without optimization. Geography is evaluated only after this RF ledger and audit are sealed. The site is absent from scientific worker policy; it appears only in the separate postdecision reporting script.

## Interpretation boundaries

This is a same-site retrospective development experiment. The historical DS cohorts and five recent controls have already contributed to earlier development. They cannot establish unseen-location generalization. Association percentage is unchanged because no native points are added or removed; position information changes through the solver and covariance assumptions.

The uncertainty proxy confounds historical propagation age with model disagreement. Older TLEs are propagated farther than the latest nominal TLE, so their spread need not equal the nominal orbit's error. Shared TLE biases can also remain invisible. [Read-only age diagnostic](covariance/diagnostics/README.md) examines this limitation without choosing another covariance model or consulting position errors.

Any future promotion requires a measurable, defensible accuracy benefit, acceptable tails and regressions, and further frozen evaluation. Numerical convergence, lower frequency residuals, and a more confident satellite identity are distinct from a more accurate position.
