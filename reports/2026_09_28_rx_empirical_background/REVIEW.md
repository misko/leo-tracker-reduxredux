# Independent pre-fit review: empirical observational reference

## Decision

The proposed leave-one-record-out comparison is a bounded, calibration-only way to choose a
better observational reference. It may proceed after the normalization and isolation gates below
are executable. The six recordings are mixed observations rather than labelled target-negative
windows. The selected distribution must therefore be called an **unconditional observational
reference**, not a learned clutter or physical absence model.

This cross-validation selects a nuisance model from reused calibration data. Its score is not
evidence for target presence or satellite identity. A later presence experiment may use the
all-calibration refit only after its mode and formulas are frozen, and must still evaluate target
and geometry claims on data excluded from this selection.

## Normalized model definitions

For each five-record training fold, let `N` be the number of paired windows and let `C(a,b)` be
the number with receiver counts `(a,b)`. Define receiver geometric distributions on nonnegative
integers using means

`m_r = (sum_i n_ir + 1) / (N + 1)`

and `g_r(n) = (1 + m_r)^-1 [m_r / (1 + m_r)]^n`. The smoothed joint count distribution must be

`p(a,b) = [C(a,b) + 32 g_0(a) g_1(b)] / (N + 32)`.

This has infinite support and sums to one. A rate-local count distribution must be

`p_q(a,b) = [C_q(a,b) + 128 p(a,b)] / (N_q + 128)`.

An unseen sample rate uses `p` exactly. Pseudowindow weights may not be applied separately to
occupied cells, because that would discard or duplicate the geometric tail.

Map every canonical receiver observation to a phase in `[0,1)` using a fixed zero origin and a
declared half-open 16-bin rule. With pooled training candidate counts `H_r(k)` and total `M_r`,

`h_r(k) = [H_r(k) + 1] / (M_r + 16)`

and the continuous density in bin `k` is `16 h_r(k) / P`, where `P` is that lane's alias period.
For a sample-rate-local histogram use

`h_qr(k) = [H_qr(k) + 128 h_r(k)] / (M_qr + 128)`;

an unseen rate falls back to `h_r`. The 128 here denotes pseudocandidates, independently of the
128 pseudowindows in the count model. Empty receiver sets have no frequency factor.

For unordered candidate sets the joint density is

`p(n0,n1) n0! n1! product_j f_0(x_0j) product_j f_1(x_1j)`.

The factorial convention is correct for a Janossy set density and makes an independent Poisson
count model reduce to `exp(-lambda) product(lambda f(x))`. Use the same measure and units for all
five modes.

## Cross-validation and leakage boundary

Leave out one complete calibration recording at a time. Recompute every fitted quantity from the
other five records: Poisson means, pooled and local count tables, geometric tails, and pooled and
local frequency histograms. Only the predeclared sample-rate labels and bin edges may exist before
the fold. A held record must not affect fallback distributions, smoothing means, or the set of
reported count cells.

Score each held record once, average its paired-window log density, and select by the equal-record
mean over the six folds. Freeze a deterministic order over the five modes and use it for exact
ties, preferably from the simplest to the richest model. Report every fold/mode score, window
denominator, count contribution and frequency contribution. Put `log(n0! n1!)` in the count
component so count plus frequency exactly reconstructs the full score. Frequency increments are
interpretable only within matched count models: `joint_frequency - joint` and
`rate_joint_frequency - rate_joint`.

After selection, fit the selected mode once on all six calibration-reception recordings and save
all normalized parameters. Do not inspect pilot held-frequency windows or any evaluation record
during fold fitting, selection, or final calibration refitting.

## Required executable gates

1. Sum count probabilities numerically over a large grid and add the analytic geometric tail;
   require unit mass for pooled and every rate-local distribution.
2. Integrate each frequency histogram to one for both receivers, pooled and rate-local, including
   alias periods that differ by sample rate.
3. Verify the Poisson set-density formula against the existing uniform Poisson implementation,
   including `(0,0)` and one empty receiver.
4. Verify finite scores for count pairs absent from training and exact pooled fallback for an
   unseen sample rate.
5. Permuting windows within a recording or candidates within a receiver set must not change a
   fit or score.
6. Perturbing the held fold, any calibration held-frequency outcome, or any evaluation outcome
   must not change that fold's fitted parameters.
7. Require six distinct held recording IDs, one appearance of each as the held fold, exact source
   hashes, and identical held denominators across modes and decompositions.
8. Recompute the selected mode and deterministic tie resolution from the emitted complete grid.

## Suitability for a later presence model

The selected all-six distribution can replace the absent-state density in a later frozen
presence comparison if it remains independent of nomination identity, Doppler predictions and
geometry, and if D, S and T use the identical reference. Freeze its source hash and parameters
before evaluation. Do not combine its cross-validation score with later held evidence or describe
the resulting absent posterior as physical target absence.

This experiment can establish that one normalized observational density predicts calibration
candidate sets better than another. It cannot establish which candidates are clutter, whether a
target was present, or whether sample-rate structure is causal.

## Runner pre-launch review

The cross-validation runner fits each mode anew inside each recording-held-out fold, scores the
held recording once, uses equal-record aggregation, applies the fixed mode order for exact ties,
and refits only the selected mode on all extracted calibration rows. Calibration-held and
evaluation lanes are rejected before their observation payloads are read. Its full-score
construction is consistent with the declared measure: the empirical module returns normalized
phase-space set density and the runner adds `-sum(n_r) log(P)` once. The count component includes
the factorial terms, so its reported frequency residual reconstructs the full score.

Before launch, strengthen the dataset identity boundary in three places:

1. Require exactly the six frozen calibration recording IDs, with at least one reception row in
   every recording, rather than accepting any dataset with two or more sessions.
2. Require every lane session ID and source window ID to be a nonempty string. Treat
   `source_window_id` as globally unique provenance. The current `(session_id, window_id)` key
   would admit the same source window twice if inconsistent session metadata were attached.
3. Test rejection of a cross-session duplicate source ID and datasets with other than six
   calibration recordings. In the result audit, require the fold held IDs to partition the
   extracted IDs exactly once, all scores to be finite, and the final model's mode and row count
   to equal the selected mode and complete calibration population.

No scoring or normalization defect was found in the reviewed runner. These identity and fixed
population checks are launch blockers because accepting a different number of records or a
duplicated provenance row would change the estimand while still producing a valid-looking
receipt. No real-data score was run during this review.

The runner now closes these blockers. Its CLI extraction defaults to exactly six calibration
recordings, requires nonempty string session/window identities, and rejects a source window ID
repeated anywhere in the calibration population, including under inconsistent session metadata.
Synthetic fixtures opt into their explicit two-record population. Installed-API verification of
the empirical model and cross-validation runner passed 17 tests in 0.06 seconds; Ruff passed on
the changed runner and tests. The reviewed sources are ready to freeze. No real-data score was
run during this review.

## Independent post-run outcome review

The bounded run completed with exit status zero. Every frozen source and input hash in the launch
receipt matches the reviewed bytes, and the dataset digest embedded in the result matches the
receipt. The independent audit reports `pass`: six held folds partition 1,356 calibration
reception windows, all fold and aggregate arithmetic recomputes, and the final selected model is
a 1,356-row refit of the selected mode.

The equal-record cross-validation scores were:

| mode | nats/window | versus Poisson | positive records |
|---|---:|---:|---:|
| Poisson | -47.099392 | 0 | 0/6 |
| joint | -46.433717 | +0.665675 | 6/6 |
| joint + frequency | -46.704211 | +0.395181 | 5/6 |
| rate joint | -46.503206 | +0.596186 | 6/6 |
| rate joint + frequency | -47.361380 | -0.261988 | 2/6 |

The pooled joint count reference is the deterministic winner. Its improvement over the
recalibrated independent Poisson model is positive in every held recording, ranging from
`+0.047481` to `+1.384516` nats/window. Rate stratification does not improve the pooled joint
model (`-0.069489` nats/window overall).

The frequency results are especially clear. Adding the pooled 16-bin phase histogram to the same
joint count model changes score by `-0.270494` nats/window and is negative in all six records.
Adding rate-local phase histograms to the rate-joint model changes score by `-0.858174` and is
also negative in all six. Thus the descriptive phase nonuniformity in the calibration corpus does
not generalize record-to-record under the frozen smoothing rule. The selected reference should
retain uniform phase density and must not import either histogram.

This is useful calibration evidence for paired count dependence and dispersion. It remains an
observational reference learned from mixed candidate sets, not physical clutter truth or a
labelled absence distribution. The all-six `joint` refit is suitable for a later normalized
signal-plus-reference implementation, provided it is frozen unchanged before evaluation and
used identically across geometry arms. No target, identity, or geometry conclusion follows from
this calibration-only comparison.

For that later additive construction, if receiver `r` contributes `s_r` signal points with
`s_r` in `{0,1}`, the density ratio to the joint reference is

`P(n0-s0,n1-s1) / P(n0,n1) * product_[r:s_r=1] {sum_i g_r(x_ri)/f_r(x_ri) / n_r}`.

Set the term to zero when `s_r=1` and `n_r=0`, mix the four signal-origin states with their
conditional Bernoulli probabilities at each shared quadrature node, and then integrate the node.
For independent Poisson counts, `P(n-1)/P(n)=n/lambda`, which cancels `1/n` and exactly recovers
the existing `sum_i g(x_i)/(lambda f(x_i))` signal ratio. Require that equivalence, `q=0`
identity, empty-set behavior, correlated joint-count ratios, and numerical total normalization
including the geometric tail before this kernel is used in an experiment.
