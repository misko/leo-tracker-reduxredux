# SOL development and comparison plan: independent single-scan localization

Status: **prepared, not executed**. Prepared 2026-10-01 with two independent
`gpt-5.6-sol` planning reviews. No new fits or RF collection were launched.

Develop a small set of approaches, then evaluate every admitted approach on
the exact same 64 DS9/DS10/DS11 scans used in the fixed-height experiment.
Prioritize a useful speed improvement, then test whether association and
nuisance changes improve accuracy. The
[model review](../../reports/2026_10_01_localization_model_review/README.md)
contains the derivations, literature, limitations, and measured bottlenecks.

## Approaches and hypotheses

| ID | Approach | Specific hypothesis | Scientific difference from control | Initial scope |
|---|---|---|---|---|
| A1 | Faster joint robust greedy | Avoiding unused Jacobians and repeated full-catalogue predictions reduces cost while preserving the fit. | None intended: retain hard associations, Student-t ν=4, priors, seeds, stopping and scheduling. | First implementation and prospective control. |
| B1 | Soft-association joint robust optimizer | Keeping plausible satellite assignments in a log-sum-exp likelihood reduces damage from premature hard choices. | Marginalize track identities conditional on the joint state; retain background and up to three distinct basins. | First accuracy challenger. |
| C1 | Reduced nuisance optimization | Eliminate the redundant clock/epoch direction and conditionally solve linear drift terms to improve conditioning and cost. | Start with the same hard joint MAP objective as A1, reparameterized/profiled; no claim of new Bayesian evidence. | Parallel numerical prototype; full benchmark only after objective equivalence gates. |
| D1 | Sequential mixture with shared nuisance state | A bounded hypothesis bank can update after completed tracks without losing useful ambiguity. | Approximate sequential Bayesian inference after broad acquisition; shared nuisance covariance retained. | Follow-on, after A/B acquisition and uncertainty tests; same 64 scans if admitted. |

A1 and C1 are numerical approaches, not independently better physical models.
B1 tests a genuinely different association objective. D1 addresses the user's
online mixture proposal but is not required to finish the first comparison.
Do not combine all improvements into one arm and attribute a result to one of
them. A later A2 may change convergence scaling or iteration allocation, but
must have a separate configuration and results from A1.

### A1: faster hard-association joint fit

Preserve the current statistical objective and control flow. Introduce mean-only
likelihood evaluation for line searches and selected-branch Jacobians for state
updates. Cache constant covariance factors and share receiver/geoid calculations
at a state. Finite-difference only the satellites actually needed by a selected
branch. Keep all-catalogue scores for reassignment and eligibility normalization.
Cache keys must include state, satellite effective times, receiver, frequency,
track times, and immutable evidence identity as appropriate.

Tests compare scores, eligibility, assignments, accepted objective sequences,
Jacobian directions, and final states against the existing numerical oracle.
Start with score tolerances rtol=1e-9/atol=1e-8 and Jacobian directional tests
with a justified finite-difference error bound. Freeze state/sequence tolerances
from synthetic conditioning tests before inspecting geographical errors.
Near ties may expose floating-point sensitivity: record and investigate them;
do not silently declare a changed basin mathematically equivalent.

Gate: synthetic and bounded real-state equivalence, no status regression on
the development panel. Replay the frozen solver on that panel through the same
new harness, acquisition, machine, and cache policy as A1. Against this matched
control, target at least 2× less fit-stage time and 25% lower median end-to-end
time; these are targets, not guarantees. Historical wall times alone cannot
establish these percentages. Report
the common acquisition cost because it places a ceiling on overall speedup.

### B1: soft association and distinct basins

Optimize the shared prior minus the sum of per-track log-sum-exp scores over
satellites **and background**. Compute normalized responsibilities and Student-t
weights; use a damped generalized EM/IRLS proposal accepted against the actual
soft objective. Visibility-dependent candidate/background priors belong in that
objective. Their gradients and discontinuities need explicit treatment.

For the first prototype score the full catalogue on every outer iteration and
every objective test. Derivatives may use an adaptive working set only if its
omitted responsibility is reported, the original full normalization remains,
and objective descent is checked. Prototype target omitted mass ≤1e-6 per track;
also require a checked bound on omitted responsibility-weighted score gradients.
Small mass alone does not bound derivative error. Start with full derivatives;
admit a working set only after this additional test passes. At visibility
discontinuities use interior/one-sided derivatives and explicit trial handling,
not a smooth gradient across the boundary. If the working set is too large,
record a budget failure rather than renormalize
a convenient top-k subset. No posterior mass claim follows from this derivative
approximation. Start the synthetic oracle without gating.

Use the same three initial seeds as A1. Merge duplicate converged solutions by
predeclared spatial, effective-nuisance, assignment/responsibility, and objective
criteria, verified on synthetic duplicate/distinct cases. Do not average distant
locations or let multiple seeds multiply one basin's weight. Initially expose
relative fit scores and responsibilities, not calibrated posterior confidence.
The review found zero nearly tied best/second pairs separated by >100 km, so a
large mode bank is not justified by the old seed-spread diagnostic.

Gate: exact enumeration checks on small cases, monotone actual soft objective,
valid background/missing-catalogue behavior, derivative/prior checks, bounded
pilot completion. Accuracy is assessed only after predictions are sealed.

### C1: effective timing and profiled drift

Replace τ and δ_s with d_s=τ+δ_s. Preserve the correlated prior
Σ_d=σ_epoch²I+σ_clock²11ᵀ. For comparison with A1's joint MAP, use the exact
profiled quadratic; reconstruct the minimizing common clock and epoch terms
when comparing objectives and states. Differential tests must retain A1's
original additive prior normalization convention. Do not substitute the
normalized marginal density with log|Σ_d| for the original profiled MAP score.
Keep the full catalogue semantics: an apparently unassigned
satellite can still affect visibility and background normalization. Do not
delete nuisance coordinates merely because no track currently selects them.

At fixed nonlinear state and IRLS weights, solve shared receiver drift by a
small regularized linear system. This is a conditional IRLS quadratic proposal,
not an exact profile or marginalization of the Student-t objective. Accept
against the same original robust objective after reconstructing coordinates.
Initially retain the A1 seed, assignment, support, and budget policies. Translate
convergence diagnostics back to original coordinates for a controlled comparison;
any altered stopping rule is a separate C2 arm.

Own tests: clock/epoch gauge invariance, dense versus rank-one prior, equality
of profiled and original minima, analytic drift solve versus dense reference,
shared versus independent error counterexample, and inactive-variable semantics.
The review's Gaussian kernels are starting oracles, not ready-made end-to-end
inference. A genuinely marginalized Gaussian variant may later use determinant
terms, but must be a separately named statistical model.

Gate: original-objective agreement, stable conditioning on synthetic stress
cases, and an observed cost or convergence benefit on the bounded pilot. A
kernel-only speedup is insufficient for promotion to 64 scans.

### D1: completed-track sequential mixture, deferred

Prototype on synthetic data first. Use deterministic completed-track order
(last observation time, then track ID), a bounded initial bank of three distinct
spatial components, and a hard cap of eight live hypotheses. Retain conditional
shared nuisance states/covariances. Fork on association ambiguity and merge only
compatible hypotheses. Report discarded mass and conservatively flag unresolved
when the configured approximation bound is exceeded.

Admit exactly two acquisition designs. In the causal design, update the uniform
disk prior with a fixed prefix once (for example by prior-weighted quadrature),
approximate that prefix posterior with a documented mixture, then process only
later completed tracks. Freeze prefix length and approximation bounds before
real fits and account for discarded mass. In the offline design, full-scan
acquisition chooses numerical starts for a batch objective using each track
once; those starts are not a sequential prior and their weights are not
sequential posterior probabilities. A data-selected three-Gaussian initializer
is not the original uniform disk. Any importance sampling alternative needs an
explicit proposal/selection correction.

The first real replay may operate offline on completed tracks, but must label
which design it uses. Causal latency measurements cannot inspect future samples.
Add an oracle detecting altered scores/weights when acquisition evidence is
accidentally replayed.

Required checks include a linear-Gaussian oracle, branching/merging, repeated
evidence rejection, shared-clock uncertainty, and sensitivity to chronological,
reversed, and seeded-permuted track order. Order sensitivity is descriptive;
only one predeclared order is the primary benchmark. Do not select the best
permutation using reference error. Full 64-scan admission requires adequate
mass accounting and bounded pilot performance. Retain the same location reset
and total single-scan budget as other arms.

## Fixed benchmark

The machine-readable [benchmark manifest](benchmark.json) binds the original
selection, sources, sessions, result controls, development units, and eight
interleaved batches. It is a planning manifest; each admitted implementation
must subsequently freeze its own code/configuration and input receipt hashes.

- **Exactly 64 recordings:** 22 DS9, 21 DS10, 21 DS11; no substitutions.
- **Independent initial conditions:** uniform 250 km map disk centered at
  latitude 38.5816°, longitude −121.4944°. Reset all position, clock/drift, satellite, mixture,
  and optimizer state per scan. Shared immutable caches are allowed; fitted
  cross-scan states are not.
- **Height:** 30.48 m MSL plus candidate-dependent NOAA GEOID18 conversion to
  approximate ellipsoid height, with the original pinned geoid grid.
- **Evidence:** same retained physical observations, ordering/exclusions,
  selected samples, causal catalogue and extended orbit banks. No raw-IQ
  reprocessing or new RF. QNAP stays read-only.
- **Baseline nuisance priors:** clock σ=1 s; satellite epoch σ=0.5 s; receiver
  drift σ=0.5 Hz/s. Reparameterizations must preserve their meaning.
- **Baseline likelihood:** normalized Student-t ν=4 with the existing signal
  and background scale matrices. Its covariance is twice its scale.
- **Truth:** reference coordinates are evaluator-only, read after prediction
  sealing. No error-driven starting points, pruning, continuation, priors,
  candidate labels, or per-scan hyperparameters. This is an interface and audit
  separation in a shared workspace, not a claim of security isolation.

### Controls, seeds, and timing

Historical controls are the sealed 51/64 primary and 63/64 two-stage results.
The separate last-scan polish remains post-hoc. Historical runtime accounting
is not assumed identical to the new harness. A1 is the new prospective control
for B1/C1, while differential tests establish its relationship to the frozen
solver. Preserve every historical artifact.

Two distinct experiments avoid hiding initialization cost:

1. **Seed-conditioned diagnostic:** reuse the original source-bound proposal
   seeds for a bounded A/B/C solver comparison. Report solver-only timing;
   never label these timings independent 90-second end-to-end scan results.
2. **Official benchmark:** each arm runs the identical deterministic common
   acquisition algorithm from the uniform prior, charging its own acquisition,
   evidence loading/validation, optimization, mode processing, and sealing time.
   Verify seed equality across arms. Do not share uncharged proposals or fitted
   states. A method-specific acquisition is a separate arm with its cost included.

Freeze the common acquisition implementation before official runs. A cached
deterministic orbit bank is evidence, not a fitted warm start. Declare a common
warm filesystem-cache policy. For each eight-unit block, run one bounded
arm-batch, review it, then run the other admitted arms on the same block before
advancing. Rotate arm order by block using the frozen list of admitted IDs;
record actual order and machine load. This pairs blocks rather than individual
timings, so report possible load/cache effects. Sequential execution within an
arm-batch is preferred for timing; two simultaneous fits is the absolute ceiling.

Use 90 s primary, with one status-triggered continuation of at most 90 s and
180 s cumulative. The scientific worker has a shorter internal deadline so a
supervisor can seal timeout/error receipts inside the external limit. Record
actual total elapsed time, including finalization; overruns are not accepted.
Continuation uses original priors and observations once, with saved optimization
state as initialization. Trigger on a predeclared numerical unresolved status,
never error. A winning unresolved optimizer mode cannot be replaced by a worse
converged mode. D1 needs separately frozen completion/approximation semantics;
do not relabel a filter checkpoint as optimizer convergence.

For A1 retain original 24-iteration-per-seed caps and stopping rules. Any common
change to budget allocation or stopping creates a new experiment, with a
matched control. Method-native numerical status and common resource/provenance
validity must both be reported; method acceptance definitions cannot be made
identical merely by giving them the same label.

## SOL ownership and concurrency

Use one coordinator and at most three concurrent `gpt-5.6-sol` workers. The
[work orders](sol-work-orders.md) are ready to dispatch. Workers share a
workspace, so file ownership is explicit; never run independent agents editing
the same common module. The coordinator approves handoff interfaces and owns
integration. This approval is an internal review, not a new user permission gate.

| Wave | SOL 1 | SOL 2 | SOL 3 | Coordinator |
|---|---|---|---|---|
| 0 | A1 physics port and numerical equivalence | B1 objective/optimizer using synthetic port | C1 timing/drift kernels using synthetic port | Benchmark adapter, receipt shape, frozen interface, scheduling |
| 1 | Finish A1 integration | Integrate B1 with reviewed common port | Integrate C1 against A1 | Run unit gates and request independent review |
| 2 | A1 author finishes; a fresh SOL verifier takes this slot | B1 bounded pilot, only granted fit slots | C1 bounded pilot, only granted fit slots | A1 pilot, admit/freeze arms, serialize expensive work as needed |
| 3 | Independent verifier audits runs and evaluation | Maintain admitted B1; no scientific edits mid-run | Optional D1 synthetic work; no interference with timed jobs | One reviewed ≤8-scan arm-batch at a time; compare and publish |

The final verifier must have authored neither an admitted estimator nor the
shared physics implementation. Start that fresh SOL task after the A1 author
finishes, keeping at most three workers active. SOL 2 additionally reviews A1
equivalence tests before official runs. The coordinator owns the final shared
protocol signature/freeze, resolves disagreements, and records findings.
Worker-facing benchmark authority and evaluator-only bindings are separate;
only coordinator/verifier receive `evaluator-bindings.json` in their work order.

Proposed ownership: shared numerical interfaces in a new private
`src/leo/analysis/localization_evaluation.py`; A1 in `localization_fast.py`; B1 in
`localization_soft.py`; C1 in `localization_profiled.py`; future D1 in
`localization_sequential.py`. Each has component-owned tests under `tests/analysis/`.
Confirm these names are free before implementation. Do not mutate public
persisted contracts or the original oracle modules. Report adapters alone may
read concrete storage; pure analyzers take contracts and narrow ports.

## Stages and bounded execution

1. **Preparation:** validate the planning manifest, freeze the small interface,
   component ownership, numerical tolerances, and metadata-only exposure log.
   Reuse existing evidence adapters; avoid building another workflow framework.
2. **Synthetic/math gates:** no real fits. Include background-only, ambiguous
   identity, missing satellite, outlier, shared timing, weak geometry, horizon
   boundary, disk boundary, duplicate observations, and duplicate basins.
3. **Three-scan development:** DS9-F001, DS10-F001, DS11-F001. Compare A1 with
   the numerical oracle, then B1/C1 with A1. At most one primary per arm/unit
   per version; preserve failed attempts and explain any revised version.
4. **Six-scan stress panel:** the three above plus DS9-F080, DS10-F131,
   DS11-F087. These include known orbit-preparation and convergence edge cases;
   they are explicitly development data. Reuse unchanged first-three receipts
   where appropriate rather than repeat tests for no reason. No error-based
   selection of additional pilot scans.
5. **Freeze admitted arms:** code, dependencies, priors, working-set/mode
   budgets, convergence rules, seeds, schedule, resource accounting, and exact
   evaluation metrics. C1 can stop at a documented negative result if it offers
   no benefit. Do not promote every prototype just to fill a comparison table.
6. **Same-64 benchmark:** one method and at most eight units per reviewed batch;
   at most two fit workers, one BLAS/OpenMP thread each. Launch each primary
   batch explicitly; inspect status before separately scheduling any allowed
   continuations. With two workers, eight units ×180 s has a 12-minute compute
   ceiling; with sequential timing, 24 minutes. Set batch wall limits to 15 or
   27 minutes respectively, including orchestration. These limits apply to one
   arm-batch, not all arms together; rotate matched arm-batches as specified
   above, with a separate review before each launch. There is no command that
   automatically launches all methods across all 64 recordings.
7. **Review each batch:** verify source/input bindings, numerical/support
   failures, observed cost, and receipt completeness. Halt for scientific or
   provenance errors; do not stop because a valid sealed error result is poor.
   Do not change the frozen method after inspecting benchmark errors. An
   amended method receives a new version and a declared development exposure.
8. **Report completed scope:** all planned units in denominators, explicit
   not-run units for halted arms, failed/unresolved outcomes, and reason for
   every early stop. Progress checkpoints are coordinator reviews, not repeated
   requests for user confirmation. Keep batches bounded and communicate results.

The worst-case arithmetic is substantial: a fully admitted 64-scan arm at the
180 s cap requires 3.2 CPU-hours, or 96 minutes at two workers, excluding setup.
This is a ceiling, not a job to launch. Pilot gates and one-batch scheduling
prevent speculative multi-method, multi-hour campaigns. Previously explored
scans remain descriptive regression data even when code is frozen prospectively.

## Evaluation and decision rules

Publish both primary (90 s) and two-stage (≤180 s) results. For each arm report:

- Completed/accepted/numerically unresolved, timeout, support, exception, and
  provenance failure counts out of 64; not-run remains separate from failed.
- Error ECDF with denominator 64, so failures remain visible; <1 km, <5 km,
  and <10 km success counts out of 64; >10 km and >100 km accepted errors.
- Conditional median/p90/worst error in meters, clearly labeled; paired errors
  for mutually valid scans and a discordant-completion table. Dataset strata
  cannot be pooled invisibly. Avoid ranking solely by accepted-only median.
- End-to-end and fit-only median/p90/max seconds, total CPU, peak memory,
  acquisition share, continuation rate, iterations, objective/Jacobian/orbit
  calls. Compare timing only under the same declared machine/cache policy.
- Distinct basin counts, background responsibilities, working-set omitted mass,
  support/observability flags. Responsibility entropy is not location accuracy.
- Region coverage and area only for a method producing properly defined
  regions; mark unavailable for score-only modes. No identity accuracy claim
  without independent identity labels. Synthetic labels are suitable for tests.

Figures: failure-inclusive error ECDF; paired per-scan error/status plot;
accuracy versus runtime; runtime breakdown; dataset table; and uncertainty
coverage/area where justified. All are regenerated from immutable receipts.

**Decision order:** first correctness/provenance, then failure-inclusive utility,
then speed/accuracy tradeoffs. Historical reference is 51 accepted at 90 s and
63 at ≤180 s, median 2,058 m/p90 5,899 m for the latter. A1 targets unchanged
science and lower cost; B1 is compared prospectively with A1; C1 must justify
its added complexity. Predeclare a practical accuracy win as ≥20% lower paired
median error with no lost accepted scans, no >10% p90 degradation, and no new
>100 km error on the fixed panel. Report all component metrics even if this
rule fails. It is a descriptive engineering rule, not a significance test.

Do not infer generalization from 64 correlated scans at one reference site or
bootstrap only three datasets as though that supplied strong uncertainty.
Independent locations and grouped held-out sessions are later validation work.
The final report may conclude that the simpler fast greedy control is best.

## Controlled follow-up ablations

Do these first on the bounded development panel, not as a Cartesian product
of full 64-scan runs. A subsequent full arm needs a specific unresolved question:

- Student-t versus Gaussian at equal scale **and** equal covariance, with both
  signal and background normalization handled consistently.
- Background/contamination alternatives only with a frozen proper density and
  calibration evidence identified separately from evaluation GPS.
- Height and timing-prior sensitivity over predeclared ranges, without choosing
  a different best height/prior for each scan.
- Scaled convergence and status-driven iteration allocation as A2/C2, isolated
  from the strict speed/equivalence comparison.

Definition of done for this planning request: a reproducible benchmark manifest,
bounded method plans, SOL ownership/work orders, numerical and scientific gates,
resource accounting, and reporting criteria. Implementation and new benchmark
results are future work.
