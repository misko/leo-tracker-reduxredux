# Independent pre-fit review: joint presence and receiver geometry

## Decision

The proposed refit is the appropriate next bounded experiment. It replaces the inadequate
independent-Poisson reference with the calibration-selected paired-count reference and estimates
signal coefficients together with occupancy and persistence. It may proceed after the executable
normalization, nesting and leakage gates below pass. It remains a calibration fit followed by an
evaluation on eight reused records, so a positive result is exploratory rather than promotion
evidence or satellite identification.

The selected background is an unconditional observational reference learned from mixed
candidate sets. Calling its hidden state `absent` is model terminology only. Neither a fitted
occupancy nor posterior state mass measures physical target presence without labelled negative
data.

## Frozen likelihood boundary

Use the `joint` model saved by the empirical-background experiment, including its all-six-record
count table, geometric tail and uniform phase density. Freeze the old 500 Hz periodic signal
kernel and old calibration feature center/scale. Exclude the old `other` shortlist component and
renormalize the original finite track-candidate priors conditional on retained nominations.

For receiver signal indicators `s_r` in `{0,1}`, the additive density ratio to the reference is

`P(n0-s0,n1-s1) / P(n0,n1) * product_[r:s_r=1] {sum_i g_r(x_ri)/f_r(x_ri) / n_r}`.

Set a term to zero when `s_r=1` and `n_r=0`. At each five-point shared Gaussian-Hermite node,
mix the four `(s0,s1)` states with the two conditional Bernoulli probabilities, then integrate the
node. The absent HMM state has relative emission exactly one. A nomination state uses the
corresponding candidate's paired relative emission. This construction preserves count dependence
under the reference and is normalized; it is not valid to substitute empirical count means into
the old Poisson likelihood.

Fit sequential predictive **relative** evidence on calibration-reception windows. Initialize each
exact recording/lane filter at its stationary absent-plus-nomination distribution, transition over
actual timestamp gaps, and update after every reception observation. Do not bridge lanes or
recordings. Absolute evaluation log density is the frozen reference log density plus the fitted
relative predictive log density. Require exact equality to the reference for the explicit null.

## Nested arms and priors

Freeze the feature indices as:

- D: intercept, receiver contrast and sample-rate term, indices `0:3`;
- E: D plus vertical/elevation feature `up`, indices `0:4`;
- S: E plus north and east, indices `0:6`;
- T: S plus signed receiver-east tilt and its up interaction, indices `0:8`.

The principal horizontal-geometry contrast is S-minus-E. S-minus-D also includes elevation and
does not isolate horizontal LOS structure. T-minus-S isolates the two nominal receiver-tilt terms.

Use the frozen beta standard deviations `[2,1,1,.5,.5,.5,.35,.35]`, occupancy-logit standard
deviation 2, and log-persistence standard deviation 1.5. The penalized objective must separate
relative log evidence from

`0.5 sum_j (beta_j/sd_j)^2 + 0.5 (logit(pi)/2)^2 + 0.5 (log(tau)/1.5)^2`.

Bound every beta to `[-12,12]`, the occupancy logit to `[-7,7]`, and the optimized **log tau** to
`[log(0.1), log(10)]`. Do not accidentally apply `[0.1,10]` as bounds to the log variable.

The exact null is a separate candidate with relative evidence gain zero and penalty zero. It is
not the finite `logit=-7` endpoint. For every arm, compare the best converged penalized gain with
zero; an exact tie selects null. If null wins, save canonical null state, mark occupancy and tau
undefined, and require every evaluation/control score to equal the reference. If neither numerical
start converges, fail the arm and the run rather than selecting a finite iterate.

## Deterministic optimization

Freeze two starts per arm. One is `beta=[-2,0,...]`, `pi=0.5`, `tau=1 s`. Define the nested second
start without ambiguity and preserve fit order:

1. D starts from the old fitted D beta, with neutral occupancy and persistence;
2. E starts from the selected D solution extended by a zero, carrying its state nuisance;
3. S starts from selected E extended by two zeros;
4. T starts from selected S extended by two zeros.

If a preceding arm selects exact null, use a declared canonical beta/state start for the next arm,
not undefined null parameters. Sequential starts use only calibration outcomes and create no held
leakage, but the order becomes part of the frozen algorithm. Record every start, convergence flag,
optimizer message, evaluations, final evidence, penalty and active bounds. Use L-BFGS-B with the
declared 100-iteration, 2,000-function, `ftol=1e-9`, `gtol=1e-5` limits.

## Evaluation and controls

Freeze all arm choices before reading pilot or confirmation held outcomes. Evaluate pilot and
disjoint confirmation panels separately, score held windows before updating, and retain original
per-record held denominators. Report absolute reference, D, E, S and T scores and relative gains,
with equal-record means and signs. Do not pool windows as independent replicates.

Apply a quarter-period frequency shift to every nomination for D/E/S/T without refitting. Apply
swap and time-reversal geometry controls to T with the exact fitted T coefficients and state
parameters. A geometry interpretation requires S to beat the reference, D, E and its shifted
nomination control with stable record signs in both panels. T additionally must beat S, swapped
tilt, reversed geometry and shifted nomination. If D alone improves, that supports only predictive
value of the nominated-signal mixture relative to this empirical reference.

## Required pre-fit gates

1. Numerically normalize the additive kernel under the full infinite-support joint reference and
   verify exact reduction to the old formula for independent Poisson counts.
2. Test empty sets, one empty receiver, unseen count pairs in the geometric tail, candidate
   permutation and receiver-paired count dependence.
3. Require `q=0` and the explicit null to reproduce reference density window-by-window and by
   record; verify absolute score equals reference plus relative score.
4. Verify transition normalization/semigroup, actual-gap use, lane reset, reception-to-held
   carryover and held score-before-update.
5. Perturbing calibration-held and all evaluation observations must leave fits, starts, selected
   arms, scaler, reference and signal kernel unchanged.
6. Assert exact D/E/S/T feature nesting, prior scales and parameter bounds. If analytic gradients
   are supplied, compare them with central finite differences on a small fixture.
7. Exercise convergence and no-converged-start failure, deterministic best-start choice, explicit
   null wins, exact-tie-to-null, and the preceding-arm-null start rule.
8. Require source hashes, disjoint calibration/evaluation sessions, unique chronological windows,
   finite complete scores and identical record denominators across all arms and controls.

## Interpretation limit

Joint fitting fixes a major mismatch in the earlier staged experiment: geometry coefficients no
longer inherit occupancy fitted around a different count model. It still uses MAP point estimates,
fixed sigma and scaler, an at-most-one-signal-per-receiver emission, one nomination state at a
time, and a reference that may have absorbed real signals. These assumptions must remain visible
in any result. A reused-panel success can prioritize a fresh confirmation; it cannot by itself
promote a geometry or identity claim.

## Executable pre-launch review

The reviewed adapter constructs the frozen joint-count probabilities correctly. It removes the
Janossy factorials to recover `log P(n0-s0,n1-s1)`, retains the full reference set density for
absolute scoring, uses the uniform-circle periodic signal ratio in consistent units, and slices
calibration-reception windows before reading observations. The vectorized calibration recursion
agrees in structure with the scalar reset filter and handles ragged lane/state arrays without
giving padded states mass. Evaluation carries reception state into held windows and uses the same
fitted parameters for shift, swap and reversal controls.

The following items must be closed before launch:

1. The nested optimizer start currently extends only the preceding beta and resets occupancy
   logit and log tau to zero. Carry the preceding selected nuisance parameters when it is nonnull;
   after a null selection use the declared canonical neutral nuisance. Test the exact D, E, S and
   T start vectors, including the preceding-null case.
2. Persist the selected fit's MAP penalty and selected start alongside relative evidence and gain.
   The candidate receipts contain these values, but the selected receipt currently drops the
   penalty required to audit the null comparison.
3. Emit and independently recompute the protocol's combined equal-eight-record reference and
   arm/control contrasts with record sign counts. The current result contains only separate panel
   summaries.
4. Document the split time contract: the generic fit kernel deliberately supports the
   mathematically valid zero-gap transition and is tested against the scalar filter, while the
   production adapter requires strictly increasing source timestamps through `prepare_lanes`.
   Retain an integration assertion so the real dataset cannot use the generic allowance to admit
   a duplicate source window.
5. Validate the embedded selected background schema, selected mode agreement and row metadata at
   the binding point before optimization. `log_density` eventually rejects a bad schema and a
   later check covers rows, but an explicit frozen-reference check gives a single auditable
   failure boundary.
6. Add optimizer tests for deterministic best-converged-start selection and the exact nested
   feature dimensions, plus result-level combined arithmetic. Preserve the existing tests for
   both-start failure, explicit-null selection, adapter count probabilities, calibration outcome
   isolation and exact null/reference equality.

No additional normalization, leakage or control defect was found. The real fit must remain sealed
until these source gates and the pending bounded synthetic runtime benchmark pass.

The final source review confirms that the blockers are closed. Nested starts now inherit both the
selected beta and state nuisance from a nonnull preceding arm and use canonical neutral nuisance
after null. Selected receipts preserve evidence, penalty and gain. The adapter explicitly binds
the embedded empirical model schema, selected mode and calibration row count. It emits combined
equal-record reference and arm/control contrasts, sign counts, and rejects any combined result
without eight distinct evaluation recordings. Tests exercise inherited nuisance, preceding-null
behavior, optimizer failure, null selection, the likelihood adapter and evaluation identity.

The generic fit kernel continues to allow a zero time gap by design and agrees with the scalar
transition; the production dataset boundary enforces strictly increasing timestamps and unique
source windows. This does not weaken the real-run protocol. Ruff passes on the joint fit, adapter,
signal kernel and their tests. The measured synthetic objective cost of 0.020--0.024 seconds gives
a projected complete fit time of roughly 135--160 seconds, inside the frozen 300-second limit.
The runner is ready to freeze and launch once the combined installed-API test receipt passes. No
real fit was run during this review.

## Independent post-run outcome review

The frozen run completed successfully in 30.63 seconds with 159 MB maximum resident memory. All
source and input hashes in the launch receipt match the reviewed bytes, all four input hashes
embedded in the result match the launch receipt, and the independent result audit reports
`pass`. Combined means, sign counts, panel contrasts, reference-plus-relative scores and held
denominators independently recompute.

All eight optimizer starts converged. Within each arm, the two starts reach essentially the same
penalized gain, supporting numerical stability at the reported solution. Every nonnull arm beats
the explicit calibration null by a large MAP margin. Occupancies are 0.488--0.537, while every
arm selects `tau = 10 s`, the upper bound. The persistence parameter is therefore boundary-censored;
these data establish neither a 10-second physical lifetime nor a resolved decay time.

The combined eight-record held results are:

| contrast | nats/window | positive records |
|---|---:|---:|
| D minus reference | +0.054800 | 5/8 |
| E minus reference | +0.021940 | 5/8 |
| S minus reference | +0.035312 | 4/8 |
| T minus reference | +0.015111 | 4/8 |
| E minus D | -0.032860 | 4/8 |
| S minus D | -0.019488 | 3/8 |
| S minus E | +0.013372 | 2/8 |
| T minus S | -0.020201 | 4/8 |
| T minus swapped tilt | -0.013633 | 5/8 |
| T minus reversed geometry | -0.000393 | 5/8 |

S-minus-D is negative in both panels: `-0.017917` in the pilot and `-0.021059` in confirmation.
Although S-minus-E is positive on average, it is positive in only one record per panel and its
combined gain is dominated by a single confirmation recording (`+0.129255`). S beats its
quarter-period shift in only four of eight records. This fails the frozen general-geometry and
horizontal-LOS criteria.

T is unsupported. It trails S overall, trails swapped tilt overall, and is essentially tied with
but slightly below reversed geometry. The panel signs also disagree: T-minus-S is approximately
zero in the pilot and `-0.040439` in confirmation; T-minus-reversal changes from `-0.006230` to
`+0.005443`. These outcomes do not support differential receiver tilt.

D has the largest reference gain, but only five of eight record signs are positive and its
quarter-period control is positive in four of eight. The narrow conclusion is that the jointly
fitted D nominated-signal mixture improves average prediction relative to the mixed observational
reference. The result does not establish target presence or identity. No geometry arm meets the
predeclared promotion conditions.

## Next diagnostic

The failed held geometry contrasts cannot by themselves distinguish a wrong directional response
from insufficient directional information. The minimum useful next diagnostic is calibration-only
and descriptive: measure, by recording/lane and nominee, the within-sequence range and sign
coverage of up/north/east and tilt features, their weighted correlation/condition number, and the
fraction of evaluation feature values outside the calibration envelope. Pair that with
leave-one-calibration-record-out coefficient/sign stability and predictive score for D/E/S/T,
declared explicitly as a post-outcome diagnostic rather than new confirmation.

If direction columns have weak within-sequence variation, severe collinearity, extrapolation, or
unstable leave-one-record-out signs, the present corpus lacks directional resolving power. If
support is broad and coefficients stable on calibration yet controls still fail across records,
the nominal LOS/tilt response is misspecified or omitted state dominates. Do not widen tau,
retune geometry, or select a new directional form on these eight held records. A revised model
would need a new frozen protocol and genuinely unused historical records or separately authorized
bounded collection for confirmation.
