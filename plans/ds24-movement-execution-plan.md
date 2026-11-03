# DS24 receiver movement validation and informative-evidence recovery

Status: execution plan prepared on 2026-10-25. Planning included source, input
and feasibility review by three SOL xhigh agents. This plan has not launched
position fits, track recovery or IQ reprocessing. New experimental results must
be versioned separately from the published studies.

## Objective and sequence

Determine whether a frozen, RF-only family-validation rule can retain useful
shared-RX1 position corrections while avoiding unsupported movements. In
parallel, test whether existing curved-track recovery adds independent satellite
information on two weakly constrained scans. Keep these interventions separate
until each has an interpretable result.

The first execution consists of preparation, the full 24-case movement-policy
trial, a two-case graph-reentry pilot, independent evaluation and publication.
Training-only noise, heavy-tail prediction, broader transfer and IQ refinement
are conditional followups with their own frozen protocols. They do not hold up
the first report.

The evidence motivating this plan is in the published
[movement witness](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_24_ds24_receiver_shift_witness/README.md),
[receiver controls](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_24_ds24_receiver_orbit_controls/README.md),
and [bottleneck analysis](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_24_ds24_bottlenecks/README.md).
Improved frequency prediction and increased association coverage are separate
outcomes from improved geographic accuracy.

## Team and ownership

Use one coordinator and three concurrent `gpt-6.1-sol` agents with
`reasoning_effort: xhigh`. Pass scoped prompts with explicit paths; do not rely
on a long inherited conversation. Reuse idle SOL xhigh agents if the thread
limit prevents spawning. Do not spawn additional workers beneath these agents.

| Owner | Responsibility | Owned outputs |
|---|---|---|
| Coordinator | Freeze protocols, assign compute, resolve scientific choices, seal results, review publication | Protocol, cohort ledger, run registry, final interpretation |
| SOL A: movement policy | Version the held-family runner, tests, two-partition trial, deterministic policy decisions | `movement/` |
| SOL B: informative recovery | Bind existing graph reentry to DS24, preserve parent evidence, run bounded two-case pilot | `recovery/` |
| SOL C: independent audit | Audit membership/causality, independently replay scores and decisions, evaluate positions after sealing, assemble report | `audit/`, `evaluation/`, `figures/` |

Suggested new root: `/srv/bulk/leo/research/ds24-movement-policy-r01/`.
If it already contains a run, inspect its state and resume only matching sealed
work, or allocate a new version. Never overwrite the earlier research roots.
Use disjoint file ownership and `apply_patch` for handwritten changes. Keep
production components, published contracts, golden fixtures and unrelated
working-tree edits unchanged.

## Wave 0: inventory and protocol freeze

The DS24 revision-2 frozen fast population contains 34 recordings; 24 have the
required frozen inputs. The ten unavailable-contract rows are DS24-0001 through
DS24-0009 and DS24-0103. This is the old tracking-contract snapshot's status,
not a statement that raw recordings or current upstream products are absent.
Do not silently replace inputs that have appeared since the original comparison.

Seal a 34-row ledger with recording/session ID, capture time, dataset mapping,
source hashes, baseline/result hashes, prior exposure, eligibility and exact
unavailability reason. Independently confirm the 24-case intersection against
the existing receiver experiment. Retain all 34 rows in coverage reporting.

Authorities:

- `/srv/bulk/leo/research/ds24-20261024-extension/manifest.json`
- `/srv/bulk/leo/research/ds25-20261024/sample.json`
- `/srv/bulk/leo/research/ds25-20261024/execution.json`
- `/srv/bulk/leo/research/ds25-20261024/compact_results.json`
- `/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/receiver/protocol.json`
- `/srv/bulk/leo/research/ds25-20261024/family_cavity/position/<case>.json`

All 24 DS24 geographic outcomes have already been examined. Label this trial
development replication; show the selected examples 0017/0095 separately from
the remaining 22. DS23 and DS25 also have previous geographic analyses. None is
an untouched holdout merely because a new method has not yet run on it.

Both experiments reset each scan independently to the original 25 x 25 km box
centered at latitude 37.906, longitude -122.545. Preserve causal TLE inputs,
original candidate universe, aliases, time conventions, prior widths and search
budgets except the explicitly declared intervention. No position pooling across
recordings, new RF collection, post-scan TLE inference, GPS-based selection or
manual satellite exclusions. QNAP remains read-only.

The evaluator alone uses 37.849061591561885, -122.48574968092912 to compute error
after RF results and policy decisions are sealed. Shared-workspace separation is
a reproducibility discipline, not a security boundary.

Wave 0 exits when source/input hashes, the complete job matrix, seeds, budgets,
policy and resource availability are recorded and independently checked.

## Wave 1A: frozen receiver-movement policy

### Models and comparisons

The baseline is the existing fresh ALGO02-v1 plus qualified causal signed phase
prior and equal-assignment-prior family cavity. The candidate adds the unchanged
RF-scaled RX1 model: 31 Gaussian coefficients, 10-second spacing, 5-second width,
50 Hz coefficient scale, RF/11.5 GHz loading. Keep its existing qualification.

Compare three complete policies on the same 24 inputs:

1. Exact saved baseline pair.
2. Existing shared-RX1 policy, including its original paired-gate fallbacks.
3. The same candidate with the new movement-support rule below.

Reuse hash-verified full-data endpoints. The new policy chooses an existing
endpoint pair; it does not add a final optimization or choose a c arm by GPS.

### Partitions, fits and predictive scores

Use two fresh seeds, `2026102504` and `2026102505`. For each seed and numeric scan
suffix construct `Generator(PCG64(SeedSequence([seed, suffix])))`. Freeze NumPy's
version, sorted active-family index mapping, actual permutations and native-ID
lists. Split the permuted family list with `numpy.array_split(..., 3)`.
Keep every receiver/channel/curved/predictive owner of each family together.

For every partition and fold, fit baseline and shared RX1 in both `c=0` and
fitted-c from the cold regional center: five phase-refresh rounds, at most
48 position steps per round. Held families contribute neither training position
factors nor curved calibration. Training predictive points retain their original
position-only role. Held phases stay at causal prior means.

At both training-only endpoints, refresh each predictor's nuisance terms using
only training observations at the fixed position. Score the full joint held
vector with shared covariance, residual quadratic and log determinant. Retain
the prior witness's Gaussian moment reference, untouched held-local priors and
native sigma multipliers 1, sqrt(2), 2; sqrt(2) remains the primary plotted scale.

Define gain as held loss at the baseline-trained endpoint minus held loss at the
RX1-trained endpoint under the SAME predictor. Sum the three joint fold gains
within each partition/predictor/c/noise-scale combination. These are dependent
cross-validation summaries, not significance levels or additive family scores.

### Exact candidate rule

Adopt the saved full-data RX1 pair only when all of the following hold:

- Its saved original RF-qualification and paired-adoption status are eligible;
  a raw rejected RX1 trial can never replace the baseline through this rule.
- The unchanged full-data physical/residual gates pass in both c arms.
- All required fits and crossover calculations are finite and complete.
- Every one of the 24 aggregate gains (2 partitions x 2 predictors x 2 c arms
  x 3 noise scales) exceeds `1e-8` objective units. This is a numerical tie
  tolerance motivated by existing score-replay precision, not a learned effect
  size or significance threshold.
- Final train and fixed-position phase-reference changes are at most 0.01 s;
  final Gamma log-precision changes are at most 1e-5.
- The final position round does not end with `iteration_budget`. The existing
  `small_step_and_improvement` and `no_accepted_damped_step` termination labels
  remain permitted and are reported as such, not described as proven stationarity.

Otherwise use the EXACT saved baseline pair and record every failure/abstention
reason. No fold dropping, new seeds, extra iterations, relaxed gates, GPS-driven
repair, displacement cap or majority-of-folds condition. Report fold disagreement.

This rule is deliberately conservative and could reject helpful changes. The
trial measures that cost. Passing satisfies the prespecified development gate;
it does not directly hold out the final full-data displacement. Evaluating full-data
endpoints on the same family data would reintroduce selection leakage.

### Implementation and tests

Reuse these sources as references; copy/adapt into a newly versioned runner:

- `ds24-receiver-shift-witness-20261025/heldout/`: `heldout.py`, `freeze.py`,
  `report.py`, `test_heldout.py`.
- `ds24-receiver-orbit-controls-20261025/evaluation/`: `matched_controls.py`,
  `run_cohort.py`, `audit_endpoints.py`, `seal_batch.py`.
- `ds24-receiver-orbit-controls-20261025/receiver/`: `adapter.py`, `adapter_rf.py`,
  `selection.json`, `protocol.json`, `position_protocol_rf.json`.

These paths are beneath `/srv/bulk/leo/research/`. The old heldout runner has
hardcoded cases, seed and output location; do not run it to produce the new batch.
Expose explicit config/root/partition inputs. Save fixed-position Gamma
convergence, which the old score artifact omitted. Use the repository virtualenv,
existing documented PYTHONPATH and one BLAS/OMP/MKL thread per process.

Required component tests: exact family removal across all factor owners; held-CFO
redaction; dense/SVD joint Gaussian score agreement; disjoint native IDs; matched
c-arm partitions and inputs; phase/Gamma/timeout abstention; exact paired baseline
fallback; tampered-seal rejection and no-overwrite behavior. Reuse relevant tests
and add only checks needed by the changed driver and policy.

Total: 144 case/partition/fold jobs, 576 train-only position fits, 1,152 crossover
vectors and 3,456 noise-scale scores. The old two-case fits are reference evidence,
not substituted for these fresh partitions. Expect approximately 1.2 GiB of
arrays from previous artifact sizes; confirm free storage before launch.

## Wave 1B: independent curved-evidence pilot

Select the two weakest scans by descending
`arms.c0.curved.all.principal_sigma_km[0]` in
`/srv/bulk/leo/research/ds24-bottlenecks-20261024/information/all_cases.json`,
breaking ties by case ID. This selects **DS24-0095 and DS24-0087**, with local
weak-axis scales 0.972 and 0.928 km. These are conditional model sensitivities,
not calibrated uncertainty intervals. Freeze this RF-only ranking and IDs.

Hold the receiver model at baseline. Bind the existing whole-curve graph reentry
in `tools/probe_ds23_single_curved_reentry.py` through a thin DS24 adapter. Keep
its published scientific thresholds: the three longest wholly unassociated
actively curved tracks, at least 12 points, full causal-catalogue screening and
at most eight refined identities including the original. Exclude the target
curve from nomination calibration and retain original-label controls.

Use whole-source proposals, unchanged physical/residual gates and matched c arms
with five phase rounds x 48 position steps. Preserve every accepted parent ID.
Preserve the existing `fit_configuration()` near-feasible constrained rescue:
only after an ordinary paired-gate failure with minimum slack at least -0.25,
at most five additional rounds x 40 steps under its original constraints.
Record ordinary and rescued endpoints separately and count both against the
same stage cap. This existing rescue belongs only to recovery; it is forbidden
in the movement-validation fits. Do not describe five x 48 as its entire budget.
The existing support-aware fallback in `tools/probe_ds23_support_aware_reentry.py`
may examine at most two failed proposals under its original mode-protection
rules; retain its result as a separately named control, never a GPS-selected
alternative. Freeze the exact candidate ordering and support semantics before
launch, and independently audit them against past recovery failure cases.

Reconstruct saved inputs using the pattern in
`ds24-bottlenecks-20261024/information/diagnose_information.py`'s `replay()`;
avoid inventory calls to `ds24_engine.context()`/`cavity_context()`, which can
execute refits.

Record whether each addition is a genuinely new active curved family, another
owner of an existing family, or predictive-only evidence. Native temporal paths
in `tools/probe_ds23_graph_seeded_paths.py` are predictive-only and restricted
to already active curved families; do not count them as new curved geometry.
Native-path expansion is deferred from this first pilot.

Keep original winner-GLRT IDs as the association denominator. Count alternate
native peaks separately, use exact ID unions, and distinguish curved calibration,
predictive likelihood and post-fit-only membership. Reuse the corrected
`ds24-bottlenecks-20261024/reporting_counts.py` or independently audited unions.

Stop after the frozen candidate budget: existing 600-second graph stage cap,
240-second support-aware cap per case, and 1,800-second overall pilot cap.
No qualified new curved family is a valid negative result. Failures retain the
baseline pair. Do not expand to the full cohort or combine with RX1 corrections
on the basis of a favorable error in these two cases.

## Compute scheduling and checkpoints

Agent count and numerical-worker count are separate. The coordinator owns the
global compute allocation; agents do not each launch their own full worker pool.
Inspect available CPU, RAM, disk and other active work before launch.

Start the movement runner with two single-threaded workers for deterministic
smoke checks included in the planned job matrix. Freeze dispatch order as case
capture-time ascending (case ID tie-break), then partition seed, then fold;
the first two jobs are the smoke subset. Do not reorder by results or difficulty.
Before launch record the resource rule: expand to six movement workers after
these jobs only if at least eight CPUs are available to this experiment and
six times their largest measured peak RSS fits within half the preflight
available RAM; otherwise remain at two. This decision uses resource receipts,
not scientific outcomes. Together with one recovery and one audit worker, the
limit is eight CPU-heavy processes globally. If the preflight cannot support
even two movement workers, revise and seal the resource protocol before launch.

Keep the existing 240-second cap per movement fold job. Freeze a 45-minute
scientific-batch wall cap from first job launch, including its smoke jobs.
Checkpoint complete jobs; at the cap terminate remaining work, record queued
and interrupted jobs explicitly, and apply baseline fallback to incomplete scans.
Do not automatically extend budgets or rerun statistical failures. A technical
repair requires a new recorded execution version and an explicit comparability
decision before reuse.

Earlier two-case jobs averaged 22.52 s, maximum 28.79 s; this projects 27-35 min
at two workers for 144 comparable jobs, but does not guarantee cohort runtime.
Retain per-job timings, termination labels, peak resources and partial results.

## Wave 2: independent evaluation and report

SOL C independently reconstructs the job matrix, family masks, native-ID union,
causal references, score components, convergence statuses and all policy decisions.
Verify result/source/input hashes and exact fallback endpoints. Preserve all
trials, including negative scores, original-gate failures and budget abstentions.
Seal RF outputs and decisions before running the geographic evaluator.

Publish the following for both c arms, separately for the movement policy and
recovery pilot:

- Full membership/availability ledger, accepted/fallback counts and reasons.
- Position mean, median, P95, worst error; paired improvements/regressions;
  qualification coverage and runtime. Show all 24 and the 22-case expansion.
- Overall receiver prediction gains separately from same-predictor movement
  support and geographic outcomes; decompose quadratic and log-determinant terms.
- Original GLRT association percentage, unique likelihood points, new active
  families, and nuisance-projected information. The movement-only policy must
  retain the original observation membership.
- Error CDFs, per-scan paired error changes, movement support versus error change,
  partition agreement and abstention-reason plots.
- For the two recovery scans, DBG01 GLRT/track views before and after, residuals,
  family influence and weak-direction information; retain rejected nominations.

Produce an MD report, figures, tables, exact sources, raw-result archives and
audit receipts. Publish the completed iteration, including negative results, to
remote main using the existing isolated publication workflow. Verify remote
commit and links, and preserve the original dirty working tree.

The first batch does not automatically create a new ALGO release. A reasonable
criterion for advancing the receiver policy is improved mean and median error
with no P95 deterioration in BOTH c arms, unchanged endpoint qualification
coverage and a complete account of the worst regression. These are descriptive
development criteria, not a significance claim. Failure or universal abstention
is a reportable outcome, not a reason to tune the gate after seeing GPS errors.

## Conditional followups and decisions

1. **Scoring robustness.** If the movement policy looks useful, freeze a separate
   test with noise estimation restricted to training families and a joint
   Student/Gamma predictive approximation. Preserve latent grouping and shared
   covariance; independent pointwise Student residuals are not the same model.
   Save sufficient design/prior data now. Validate its numerical error before
   using it to choose positions; never tune it to recover favorable GPS cases.
2. **Transfer.** Audit exposure records for existing unexamined recordings. If
   found, select 8-12 by a frozen chronology/session rule before opening outcomes.
   Otherwise use DS23/DS25 only as previously examined cross-cohort transfer,
   maintaining per-scan inference and distinct fast/adaptive reporting. Do not
   claim independent-location validation from these same-site datasets.
3. **Recovery expansion.** Expand only after identifying a reproducible RF-valid
   evidence addition and explaining its information contribution. A gain in
   association percentage alone does not qualify it. Preserve separate baseline,
   receiver-only and recovery-only arms before testing a combined method.
4. **Existing-IQ precision control.** Conditional on an existing authorized reader
   exposing hash-verified windows. Direct raw-manifest reads for 0095/0087 currently
   return PermissionError; do not alter ACLs, silently substitute recordings or
   collect new RF. The main experiments do not depend on resolving this branch.

For the IQ branch, begin with one selected scan and a 600-second assay cap.
Freeze complete active-curvature curves per RX/band using existing 12-96-point
selection rules; retain every selected window and native ID. Reuse
`tools/local_pilot_refinement.py`'s `PilotWorkspace` and canonical update patterns
in `tools/probe_ds23_refined_curve_position.py`. The DSX01 remeasurement helper is
hardcoded to 2.5 MS/s and cannot be reused unchanged for 10 MS/s DS24.
Require 10 MS/s synthetic closure, correct acquired/residual CFO provenance,
timing and frame-support checks before real processing. Compare fixed-label,
fixed-mask precision first, with unchanged noise model, aliases and both c arms;
end-to-end recovery is a separate experiment. Unsupported/access-failing inputs
produce a documented blocked branch, not delayed publication of other results.

## Agent launch briefs

**A:** Implement Wave 1A in your owned directory, following this protocol exactly.
Read the frozen source studies; do not alter them. Deliver tests, deterministic
job records, all covariance/score artifacts and explicit policy source bindings.
Request compute allocation from the coordinator before launching fits.

**B:** Implement only the two-case Wave 1B adapter and bounded existing-method
pilot. Select and nominate from RF evidence only. Protect parent membership and
mode semantics. Separate new curved families from predictive-only coverage.
Record IQ access feasibility, but do not let that block graph reentry.

**C:** Independently audit Wave 0 and the method/driver before execution; build
decision and score replay checks while A/B implement. Keep geographic reporting
separate until results are sealed. Publish full denominators, failures, negatives,
figures and provenance through the isolated publication workflow after review.
