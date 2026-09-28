# Independent pre-fit review: target-presence geometry filter

Final artifact note: the audit entry-point mismatch identified during post-run review was corrected before execution. `audit.json` now reports `status: pass`, including independent raw-count absent-score reconstruction, exported held-score sums, source hashes, exact grid keys and combined equal-record arithmetic. This correction changed only the audit utility, not the frozen experiment or its results.

## Decision

The proposed filter is a reasonable bounded correction to the whole-block nomination assumption.
It may proceed as an exploratory, no-refit state-handling experiment after the executable gates
below pass. It cannot establish target presence, satellite identity, calibrated clutter truth or
a general geometry gain. All eight evaluation recordings have already informed the research
sequence, so even a clean held result is reused exploratory evidence.

The most important decision rule is simple: **if calibration selects `pi = 0`, the model has
legitimately abstained and the experiment has no positive target or geometry result.** Do not
override that choice, remove the null, widen the grid, or report a conditional positive result
from a nonzero occupancy that lost to the null.

## Executable pre-fit review

The implementation of the reset transition and forward recursion matches the frozen model. It
initializes at `v`, uses actual elapsed time, transitions before each later emission, carries the
reception posterior into held windows, and scores each held observation before updating. The
state grid is selected separately for D, S and T from calibration-reception windows, with one
canonical `pi = 0` entry and the specified deterministic tie rule. The confirmation panel is
evaluation-only and session-disjoint from the pilot. Swap, reversal and quarter-period controls
reuse frozen coefficients and the already selected state parameters.

The initial review identified the following audit gates:

1. `prepare_lanes` and `emission` silently treat the final component as `other`. Validate that
   there is exactly one `other`, that it is last, that every preceding component is a
   `track_candidate`, and that prediction/component cardinality agrees in every window. A
   malformed or reordered document must fail rather than turn a catalogue component into the
   absence boundary.
2. Validate per-lane source-window uniqueness, strict UTC chronology, allowed and ordered roles,
   and nonempty reception and held populations. The low-level filter accepts equal timestamps;
   the dataset boundary therefore needs the stronger experimental-contract check.
3. Export the unique calibration-reception denominator with every arm's grid. Assert on the real
   prepared emissions, per lane and in aggregate, that `pi = 0` equals the analytical absent
   density exactly. The current synthetic test replaces the emission function and does not
   establish the units, empty-receiver behavior, or component slicing of the actual likelihood.
4. Compute calibration likelihood only for the selected reception rows. The current code builds
   all-window likelihood arrays and masks afterward. The unused held signal arrays are zero, so
   this does not presently create statistical leakage, but a selected-row likelihood is the
   enforceable boundary and prevents a later implementation change from reading sealed outcomes.
5. Add the protocol's candidate-permutation, actual absent-density including an empty receiver,
   real-emission null equality, and run-boundary held/evaluation perturbation tests. Current
   coverage establishes the recursion and a monkeypatched selection boundary, but not these
   end-to-end invariants.
6. Emit the combined equal-record eight-record comparisons needed for the decision rule. Also
   retain enough state output to audit conditional nomination entropy, expected refreshes, and
   state mass at the reception boundary and after held filtering. Per-panel means and marginal
   presence traces alone cannot reproduce those required summaries.

These are pre-fit integrity and reporting blockers, not evidence against the state model. No real
fit or held-score run was performed in this review.

The structural gates are now implemented: the runner rejects malformed component ordering and
cardinality, duplicate windows, non-increasing timestamps, invalid or interleaved roles, and
lanes lacking either temporal population. Each grid export includes its calibration-reception
window denominator and analytical absent score, and selection raises if the real `pi = 0`
forward score differs from that density. The broader test suite now covers the real emission null,
outcome perturbation and candidate permutation; combined decision summaries and conditional
entropy are emitted by the runner. Installed-API verification passed 21 presence filter,
geometry and validation tests in 0.28 seconds, and Ruff passed on the changed runner and tests.
No real fit or held-score run was performed during this review.

## Independent post-run outcome review

The frozen run completed with exit status zero in 11.41 seconds and 148 MB maximum resident
memory. Every source and input digest in `launch.json` matches the bytes reviewed after the run,
and the three input digests embedded in `results.json` match the launch receipt. All three arms
selected the upper grid corner, `pi = 0.5` and `tau = 10 s`, from 1,356 calibration-reception
windows. Their null forward scores differ from the independently accumulated analytical absent
score by only `-7.28e-12` log units. Selection at both upper boundaries is a limitation; the grid
must not be enlarged in response to these held results.

The combined equal-record arithmetic over eight reused evaluation recordings recomputes as
follows:

| contrast | nats/window | positive records |
|---|---:|---:|
| D minus reference absent | +0.073430 | 5/8 |
| S minus reference absent | +0.006946 | 2/8 |
| T minus reference absent | +0.005463 | 3/8 |
| S minus D | -0.066484 | 3/8 |
| T minus S | -0.001483 | 3/8 |
| T minus swapped tilt | +0.001947 | 6/8 |
| T minus reversed geometry | -0.005117 | 5/8 |

S is below the reference absent model in all four pilot records. In the disjoint confirmation
panel it is above that reference in two of four records, but it trails D by `-0.101063`
nats/window; pilot S-minus-D is also negative at `-0.031904`. Thus S fails the frozen primary
criterion despite its slightly positive combined reference contrast. This result reverses the
ranking seen under the old forced whole-block nomination mixture: the explicit presence model
mostly benefits D, so the earlier S-minus-D gain was not robust to the state assumption.

T also fails: it trails S overall and loses to reversed geometry overall. A small positive result
against swapped tilt cannot support a tilt claim when the nested and reversal controls fail. The
frequency-shift controls are panel-dependent as well: S-minus-shift is `-0.000940` in the pilot
and `+0.015356` in confirmation. None supplies stable directional or identity evidence.

The experiment supports only the narrow observation that the frozen D nominated-signal mixture,
with calibration-selected persistence, predicts these reused candidate sets better than the
assumed reference clutter density on average. The 5/8 D sign count, inadequate unlabelled
background model, boundary grid choice and reused panels preclude a target-presence claim. The
geometry arms do not meet the protocol's promotion rule.

One reporting defect remains outside the frozen model result: the current `audit_results.py`
entry point passes two arguments to an `audit` function that requires four, so it cannot yet
produce the advertised independent `audit.json`. Correct that receipt generator and run it
against the frozen result without changing or rerunning the model.

## Frozen state model

For each recording and exact lane, define one absent state plus every retained finite-prior
track-by-candidate state. Reconstruct nomination weights from the original finite training log
priors in log space and renormalize them conditional on the retained nominations. Exclude the old
`other` component: omitted catalogue mass describes shortlist incompleteness and is not a
target-absence probability. Preserve track identity even when two tracks nominate the same
catalogue number; disclose this duplication rather than merging states after training.

Occupancy `pi` is a new state-model probability independent of retained catalogue mass. The
stationary vector is

`v = [1 - pi, pi * w_1, ..., pi * w_H]`.

For elapsed time `dt`, use exactly

`P(dt) = exp(-dt/tau) I + (1 - exp(-dt/tau)) 1 v^T`.

This transition retains the current absence or nomination with the exponential survival term
and otherwise refreshes to absence or any retained nomination. Initialize each lane at `v`,
transition before each subsequent emission, process windows in strict UTC order, carry the
filtered distribution across the reception-to-held boundary, and score every held window before
its observation updates the filter. Start a new filter for every recording/lane. Do not bridge
unrecorded lanes or recordings.

The `pi = 0` case is one exact absent-only model. `tau` is undefined there; emit one null grid
entry rather than duplicating the same null for every tau. Its likelihood must reproduce the
analytical frozen uniform-clutter score window by window and by recording.

## Emissions and parameter boundary

Reuse the frozen sigma=500 Hz, RX clutter intensities, feature center/scale and D/S/T coefficient
vectors from the original calibration fit. Do not optimize or recalibrate an emission parameter.
The absent state uses the frozen uniform periodic Poisson clutter set density. Each present state
uses the corresponding original D, S or T complete candidate-set emission, including both
receivers, the shared five-point window state, visibility, qualified empty sets, every passed
candidate and all clutter/count normalizers.

This experiment tests state handling, not a new emission fit. The at-most-one signal-origin
candidate per receiver remains an assumption and must remain in the limitations. The hidden
state also permits only one retained nomination at a time. Simultaneous emitters or overlapping
physical episodes are not modeled; improved density cannot be interpreted as proof that the
single-state description is physically correct.

## Calibration-only grid selection

Use the original six calibration recordings' reception windows only. Seal their held windows and
all eight evaluation recordings during selection. The frozen grid should contain the single
`pi = 0` null plus the Cartesian product

`pi in {0.01, 0.1, 0.5}`, `tau in {0.1, 1, 10} seconds`.

For each arm separately, select `(pi, tau)` by maximum calibration-reception marginal likelihood,
summed with one contribution per paired window and the same treatment of recordings. D, S and T
receive the identical grid and therefore equal state-model capacity. Freeze a deterministic tie
rule before evaluation: prefer smaller `pi`, then smaller `tau`; the null wins any exact tie.
Record every arm's complete grid scores and unique-window denominator.

Arm-specific grid selection is appropriate for this first question: can each already-frozen
emission model use the same bounded presence mechanism? It also changes the meaning of S-minus-D.
That contrast combines different frozen emission coefficients with each arm's calibration-chosen
state nuisance; it is not a coefficient-only geometry ablation. Report both selected grid points
and do not attribute the whole contrast to LOS terms. A later joint presence/emission refit would
be a separate experiment.

Whenever an arm selects `pi = 0`, that arm must reproduce the exact null score and be independent
of tau. Any difference is an implementation failure. The absent reference remains a required
held comparator for every nonzero arm.

## Required pre-fit tests and audits

Before reading held scores, require:

1. Every state prior normalizes in log space; zero/underflow display probabilities are recovered
   from finite training log priors without flooring or temperature changes.
2. Each transition matrix is finite, row-stochastic and has stationary distribution `v`; limits
   at `dt = 0`, very large `dt`, `pi = 0` and one nomination are tested.
3. The forward recursion agrees with brute-force enumeration on a short synthetic sequence.
4. Candidate permutation with matching state permutation leaves evidence unchanged.
5. The absent state reproduces analytical clutter set density, including frequency units and
   empty receiver sets.
6. `pi = 0` reproduces every existing frozen clutter record total and is tau-independent.
7. Windows are unique, chronological and role-disjoint; reception filtering precedes held
   score-before-update; denominators are identical for D/S/T/null.
8. Perturbing calibration-held or any evaluation outcomes cannot change any arm's grid selection,
   nomination weights, transitions or emission parameters.
9. The six calibration and both four-record evaluation panels retain their exact source hashes
   and recording membership. No historical cache may enter both calibration and evaluation.
10. All grid and held likelihoods remain finite under the fixed resource bound. Failure is a
    no-go, not permission to remove windows or tune the grid.

## Outcome reporting

Report absolute null, D, S and T held log predictive density by recording, not only pairwise arm
contrasts. Report the chosen grid point, all calibration grid scores, held denominators, occupancy
posterior summaries, nomination entropy conditional on presence, refresh counts or expected
transition summaries, and state mass before and after each role.

Keep presence probability and nomination probability separate. A high posterior presence is a
model state, not observed target truth. A concentrated conditional nomination is not satellite
identification. If nonzero presence beats the null, describe it as evidence that the frozen
nominated-signal mixture predicts candidate sets better than the frozen reference clutter model.
The background model has no labelled negative truth and must be called a **reference clutter
model**, never learned target absence.

The geometry decision requires more than S beating D:

- S must select nonzero occupancy;
- S must beat the exact absent reference and the presence-filtered D arm on the equal-record held
  score across the eight reused records, with pilot and disjoint panels also reported separately;
- gains should have stable record signs in the pilot and disjoint panels separately;
- elevation-only and nomination-null controls remain necessary before a directional LOS claim;
- T remains unsupported unless it independently clears its swap and reversal controls.

With eight reused records, mixed S-minus-null signs remain a no-promotion outcome even if the
combined mean is slightly positive. Do not pool windows as independent replicates or infer a
target-presence confidence interval from them.

## Background audit limitation

Invisible windows and empty candidate sets are useful model checks, but they are not honest
labelled target negatives. The audit found **zero all-invisible windows among 1,356 calibration
reception windows**, so there is no target-negative subset from which to learn a new background.
Catalogue/visibility error, other Starlink emitters and detector misses remain possible. A
calibration-only audit may test whether the uniform Poisson reference matches marginal count and
frequency distributions; it cannot turn mixed windows into ground-truth absence.
If dispersion, receiver/lane variation or periodic-frequency nonuniformity is material, freeze a
richer reference model before a later evaluation. Do not let occupancy or geometry coefficients
serve as an implicit correction for a visibly inadequate clutter process.

## Next step after this bounded experiment

If the presence filter selects nonzero occupancy and beats the reference null consistently, the
next confirmation should reserve new recordings and freeze three nested pieces separately:

1. a calibration-only reference clutter model with adequacy diagnostics;
2. a target-presence process with window/episode transitions;
3. conditional nomination and geometry emissions.

That separation is the minimum path to deciding whether geometry improves association, rather
than merely suppressing a harmful nomination. No new RF is required for the present bounded
filter; fresh or truly reserved evidence is required before scientific promotion.
