# Position model update and performance benchmark

Status: research implementation and archived-data benchmark completed with the
limitations below; production configuration is unchanged. Independent validation
and operational promotion remain outside the completed work.

## Execution record — 2026-09-21

Implemented the fixed-identity orbital model, causal phase-state preparation,
normalized robust correlated-noise likelihood, per-fit noise estimation, nested
subset runner, independent synthetic coverage evaluator, and an experimental
shared-satellite identity-mixture model. Component tests include held-out
isolation, degenerate geometry, causal phase versus clock preparation, candidate
symmetry, missing evaluation support, and failure denominators.

The first sealed fixed-identity replay reached **328 m** horizontal error. Exact
SGP4 checking found a maximum phase-approximation difference of **0.104 Hz**.
This does not beat the earlier exploratory 275 m estimate. A distant-start
benchmark caught a clipped-simplex noise-bound trap; a red/green regression
test and training-objective-only interior restart recover the same solution
without inheriting the full-data position.

The nominal local 95% region misses the known position. Two hundred synthetic
trials also expose undercoverage under added drift. We therefore do not claim
calibrated confidence or general sub-kilometre accuracy. Receiver clock/drift
sharing, full integration of the identity and correlated-noise models, and
independent-site validation remain separate acceptance work; no new RF campaign
or production promotion is implied.

The final paired matrix contains 176 runs. Full-data error is 328.4 m; exact
quarter/half observation medians among successful fits are 399.4/372.7 m.
Formal seeded subsets converge in 63/80 cases; all 17 failures are retained.
The separate joint-identity prototype converges but does not improve its matched
reference (2,007 m becomes 2,040 m), and its approximation/support audit does not
qualify it for promotion. Fifty focused and related regression tests pass.

Results, figures, and machine-readable artifacts:
[formal positioning benchmark](reports/2026_09_21_formal_position_benchmark.md).

## Objective

Turn the promising archived position estimate into a reproducible estimator with
measured accuracy, uncertainty, failure rates, and sensitivity to available data.
Compare the full dataset with nested halves and quarters to distinguish the value
of observation density, independent passes, and elapsed observation time.

The reference experiment used 622 episodes and 21,702 observations. Its exploratory
fixed-identity orbital model reduced horizontal error from approximately 4,859 m
to 275 m and randomized held-out RMS from 157.09 to 78.63 Hz. Identity mixing alone
did not improve that cohort. These results motivate the work; they are not an
accuracy guarantee or a target to tune against.

Reference: [archived comparison and artifacts](https://github.com/misko/leo-tracker-reduxredux/blob/3f9867ac1c6277e709c6c232ea2e5f02604195c2/reports/2026_09_21_uncertain_position_comparison.md).

## Non-negotiable boundaries

- Use archived RF initially. No new collection or production deployment is part
  of this plan.
- Require both TLE epoch and documented catalogue availability before capture
  start. Missing availability evidence is an explicit exclusion, not an assumed
  causal input. Later TLEs belong only in separately labelled diagnostics.
- Ground truth is available only to the evaluator after inference is sealed.
  It cannot choose identities, priors, solver starts, thresholds, or subsets.
- Keep randomized held-out observations for TLE residual evaluation. Independent
  sessions test localization generalization; they do not introduce a chronological
  TLE-residual rejection gate.
- Preserve unsuccessful runs and all prespecified variants. Lower RMS alone does
  not establish better positioning.
- Reuse numerical components, storage ports, and existing job infrastructure.
  Do not add another queue, mutable public contract, or storage dependency inside
  an analyzer. All QNAP access remains read-only.

## 1. Formalize a minimal statistical model

For observation i in track j, use:

`observed_frequency_i = Doppler(position, orbit_of_identity_j + correction, time_i + clock_error) + source_offset + receiver_drift + noise_i`

| Unknown | Sharing and constraint |
|---|---|
| Receiver position | One stationary position per campaign; fix altitude initially and label the result horizontal-only |
| Satellite identity | Competing candidates plus an unassigned component; identical correction rules for every candidate |
| Orbital correction | Start with the tested phase-rate correction shared by satellite, using causal TLE age and an explicit prior |
| Clock error | Share by a documented timing-continuity group; constrain using measured timing evidence |
| Frequency offset and drift | Share only where receiver continuity supports it; retunes may require separate offsets |
| Noise | Robust distribution with within-track correlation and an independent measurement-noise component |

Write down the normalized likelihood, units, priors, and parameter-sharing graph
before implementation. Replace the current arbitrary Hz conversion of orbital
penalties with probabilistically defined scales learned on development data.
Freeze those scales before evaluation. If an approximation profiles frequency
offsets instead of marginalizing them, name and test that approximation.

Begin with fixed identities to isolate the orbital-model change. Then combine
identity uncertainty with the same orbital prior for every candidate. Retain
unassigned probability and full-catalogue prior mass. Repeat omitted-candidate
likelihood checks after fitting; a shortlist validated at one location does not
certify another location or the global search.

Do not multiply by a second heuristic confidence score derived from the same
residuals. Identity ambiguity, correlated noise, and geometry should influence
position information through the model. Report each separately for interpretation.

Deliverable: an equation/specification document plus a pure numerical component
with explicit input/output structures, convergence diagnostics, and deterministic
configuration. Retain the legacy estimator as a comparison implementation.

## 2. Freeze the benchmark manifest

Record before running new comparisons:

- Capture, analysis, catalogue, and observation hashes; unique observation IDs.
- RF-derived track/pass grouping, timestamps, channel/edge, RX, and sample rate.
- Causal catalogue cutoffs, timing evidence, exclusions, and reference commit.
- Development versus evaluation campaigns, immutable hyperparameters, candidate
  policy, solver starts, seed list, compute limits, and failure definitions.
- Original randomized fitting/evaluation masks for the matched historical replay.

Use the published 622-episode cohort first. Evaluate expanded tracklets separately
so a model change is not confused with a data-selection change. All models in a
comparison receive exactly the same selected observations and catalogue policy.

Historical reproduction may use the published initialization, but label it as a
local replay. For the data-volume benchmark, do not initialize reduced datasets
from a full-dataset position or reuse its fitted identities, offsets, or orbital
corrections. Use a common external prior and deterministic starts independent of
target RF. Report global acquisition and local refinement as distinct experiments.

## 3. Full / half / quarter sampling design

Use 20 predetermined seeds (0–19) for randomized selection. Assign a deterministic
random ordering within each declared stratum; take nested prefixes so
`quarter ⊆ half ⊆ full`. Use stable IDs, a documented hash/PRNG version, and explicit
rounding. Never select according to observed error, residual RMS, or inferred
satellite identity.

| Experiment | Retain 100%, 50%, 25% of | Preserve | Question |
|---|---|---|---|
| Observation density | Fitting observations within every track | Campaign coverage and track temporal support as closely as feasible | Does denser sampling improve the estimate? |
| Independent support | Whole RF pass groups | Full campaign duration, balanced by time/channel/sample rate where feasible | Do more independent passes and geometries help? |
| Duration | Consecutive recording windows | Natural capture cadence within each window | How does accuracy develop with elapsed time? |

For density, order observations within prespecified temporal bins to avoid
accidentally removing one end of a track. Do not duplicate points or silently
force minimum counts. Report actual span, retained count, and tracks that become
unusable. A pass group must keep correlated fragments together, using RF/time
grouping established without the evaluated satellite associations.

Duration windows are nested contiguous intervals, not randomly scattered
observations. Use a prespecified set of admissible start times; report overlap.
The primary start is the campaign beginning. Additional starts are sensitivity
replicates, not independent trials. Include operational durations of 30 minutes,
1, 2, 4, and 8 hours where the archive permits.

Define 100% as the complete fitting pool after the fixed evaluation split, not
100% of observations including held-out values. Preserve one evaluation pool
across the density subsets. For whole-pass removal or shortened duration, an
excluded track may have no fitted offset: either evaluate its genuinely prior
predictive distribution or mark its residual score unavailable. Never fit its
offset on evaluation samples to manufacture a common RMS. Compare shared
supported evaluation IDs separately and publish the evaluation denominator.

Refit from scratch for each subset. The identical full-data run can be reused
across seeds; do not count it as 20 independent results. Treat seed-to-seed spread
as subset sensitivity, not a confidence interval for performance at new sites.

## 4. Implement in ordered, testable stages

| Stage | Implementation | Exit evidence |
|---|---|---|
| A | Manifest, deterministic sampler, evaluator, baseline replay | Exact memberships and baseline reproduction within frozen numerical tolerances |
| B | Formal fixed-identity orbital model | Synthetic recovery, held-out isolation, exact propagation checks, matched real-data comparison |
| C | Correlated-noise treatment and uncertainty | Duplicate/correlation tests, identifiable and degenerate synthetic geometries, coverage measurements |
| D | Joint identity and orbital uncertainty | Symmetric candidate treatment, unassigned handling, multiple modes, final-mode catalogue-tail checks |
| E | Full/half/quarter and duration matrix | Paired results, failures, costs, and all specified figures |
| F | Independent-session and later multisite validation | Frozen configuration evaluated without truth-driven changes |

Reuse `identity_mixture.py` and the existing orbital, weighting, export, and
evaluation tools where appropriate. Add a small manifest/sampling utility and
benchmark runner rather than replacing the pipeline. Run A–C before committing
the full matrix to expensive joint-identity fits. Any deliberately reduced pilot
matrix must be labelled incomplete; do not extrapolate it to the full benchmark.

Jobs are identified by input/configuration hashes, model, sampling method,
fraction, and seed/window. Use bounded concurrency, atomic outputs, and existing
queue/retry facilities if queued. Resume completed jobs without rerunning them.
Persist inference separately from truth-based evaluation.

## 5. Red/green test plan

Add failing tests for each required behavior before implementation. Scientific
fixtures are reviewed explicitly; never regenerate a golden result merely to
make a test pass.

| Test | Failure it must catch | Passing behavior |
|---|---|---|
| Nested sampling | Non-nested, reordered, duplicated, or seed-unstable membership | Stable quarter/half/full sets, documented rounding and exact IDs |
| Group integrity | Related pass fragments split across keep/drop selection | Whole declared groups retained or removed |
| Data isolation | Held-out values, truth, or full-data fit influence a subset fit | Perturbing those inputs leaves fitted subset parameters unchanged |
| Causal catalogue | Future epoch, late archive snapshot, missing provenance | Reject and record the specific reason |
| Nuisance sharing | Incorrect offset/clock sharing across retunes or resets | Synthetic continuity/reset cases recover the intended structure |
| Identity symmetry | Only the old winner gets an orbital correction | Candidate-order permutation preserves likelihood and inferred position |
| Ambiguity/outliers | Forced identity or overconfident false fix | Multiple plausible modes or unassigned support remain visible |
| Correlated evidence | Copied samples falsely count as independent information | Duplicate IDs rejected; correlated synthetic samples do not yield IID certainty |
| Identifiability | Narrow geometry reports an unjustifiably small ellipse | Broad/multimodal uncertainty or explicit insufficient-information status |
| Numerical agreement | Phase interpolation or clock/orbit confusion biases Doppler | Agreement with exact propagation within frozen tolerances |
| Catalogue truncation | Fitted mode gains an omitted plausible identity | Full-catalogue check detects it and expands support or fails explicitly |
| Restart/publication | Retry overwrites another result or publishes partial artifacts | Idempotent completion, atomic JSON/figures, matching manifest hashes |

Use synthetic cases with known position, orbit perturbations, timing error,
correlated noise, bad points, and competing satellites. Include both correctly
specified and deliberately misspecified noise/orbit scenarios. Check reported
50%, 90%, and 95% region coverage over independent simulated trials; use binomial
uncertainty when judging coverage rather than demanding exact percentages.

Real-data regression checks establish numerical reproducibility, not a required
improvement. A valid negative result must pass the benchmark. Hardware, database,
and QNAP integration requirements must have explicit test markers.

## 6. Required report and figures

Publish machine-readable per-run metrics and a report containing:

1. Position error versus 25/50/100% retained data: separate panels for density,
   complete passes, and duration; paired model curves and subset spread.
2. Error versus actual observation count and independent pass count, with the
   corresponding satellite count, temporal span, and effective information diagnostics.
3. Paired position-error changes from the legacy estimator; include every failed,
   ambiguous, or excluded run in the accounting.
4. Estimated uncertainty-region size versus actual error, plus coverage curves
   from simulations and sufficiently independent real evaluation campaigns.
5. Likelihood maps, parameter correlations, group-deletion influence, and examples
   where long ambiguous tracks differ from short informative tracks.
6. RMS/predictive score versus position error, with comparable scoring populations
   identified; runtime and peak memory versus retained data.

Report median, 90th and 95th percentile horizontal error where sample size supports
them; include uncertainty and denominators. Twenty overlapping subset replicates
cannot establish a reliable real-world 95th-percentile accuracy claim. Distinguish
failure rate from error conditional on successful fixes. Use station/session/pass
grouping for inference about generalization rather than resampling individual RF
points as independent trials.

## 7. Acceptance and promotion

Implementation is complete when all stages being claimed have passing tests,
reproducible manifests, complete result/failure accounting, readable figures, and
verified JSON links. Numerical tolerances and the independent validation sample
size are frozen in the manifest before execution.

Scientific success requires improved position error on matched data without an
unreported increase in failed fixes or underestimated uncertainty. Sub-kilometre
median and 95th-percentile error are operational targets, not assertions about
this archive. Claim them only on adequate independent evaluation data with
uncertainty on those estimates.

If adding samples lowers RMS but worsens position, or subset estimates disagree
beyond their uncertainty, retain that result and investigate model bias and
geometry. Do not tune against the known coordinate until the target is met.

Production adoption is a later decision after frozen prospective evaluation.
This plan's immediate deliverable is a tested research estimator and an honest,
repeatable characterization of when additional data helps.
