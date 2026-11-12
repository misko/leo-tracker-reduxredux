# Algo07v4 baseline and algo07v5 goal

Algo07v4 preserves the full-budget native solver as a separately identified
implementation. Algo07v3 keeps its original solver. The provisional algo07v5
runtime is registered for evaluation with an explicit initial-control reuse
policy. It has not met the speed target or completed independent DS26 qualification.

## Proposed slash goal

```text
/goal Develop algo07v5 toward at least 2x complete-worker speed versus the frozen
algo07v3 baseline. Keep the published algo07v4 implementation fixed as the
comparison and rollback. Another 2x versus algo07v4 is a stretch target.
Measure the speed versus localization-accuracy frontier before choosing an
approximation budget. Keep algo07v4 fixed as the rollback and comparison point.

Use tools/evaluate_algo07.py run --profile quick for DS26-0002/0066/0102.
Use plan --profile full, then run --profile full, for the frozen DS26 inventory.
Pass --version algo07v4, --native-manifest FILE and a fresh --output DIR for
the fixed baseline. Select the provisional candidate with --version algo07v5.
Use the documented pinned Python environment and plan before a full run.
Keep candidate policies explicit in requests and the CLI. The annotation
optimizer experiment uses --annotation-training-policy lbfgsb-full5-625-v1.
Start every experiment with a bounded component replay, then
run the quick screen. Qualify finalists on the independent remaining scans.
Keep all 159 expected inventory members visible, including the currently
unavailable DS26-0172. Report completed, failed, timed-out and missing counts.
Never count an incomplete run as a speedup or silently shrink the denominator.

Report complete-worker wall and CPU time, stage costs, actual solver work,
and both c=0 and fitted-c results under matched data, candidate policies,
priors and search budgets. Report GPS error median/p90/p95/max, paired error
changes and all outliers separately from frequency fit, ownership and audit
changes. GPS may score completed inference; it must not select settings or
enter inference. Separate development scans from held-out qualification.

Prioritize predictive annotation, inclusion/retry, initial search and
admission. Look for repeated work that can be reused or moved earlier before
reducing budgets. Preserve negative experiments. Keep one change per measured
attempt and record its speed, accuracy, failures and decision. Use alternating
timing repeats on representative quick cases before claiming a stable win.
The primary speed metric is the baseline total wall time divided by candidate
total wall time over all matched complete available DS26 members. Also report
per-scan ratios and timing tails. A component ratio cannot satisfy this target.
Stop when the target and chosen accuracy budget pass independent evaluation,
or report the measured frontier and the remaining bottleneck explicitly.
```

The accuracy budget is intentionally open. A measured frontier lets the operator
choose a useful tradeoff rather than assume that every numerical difference
invalidates a candidate. A candidate still has to produce valid, complete
scientific results and publication artifacts.

## Measured starting point

The original and native runs use the same full precision-update budget.
These are one sequential pair per development scan, not population estimates.

| Scan | Original wall seconds | Native wall seconds | Original/native ratio |
| --- | ---: | ---: | ---: |
| DS26-0002 | 184.391012 | 117.959557 | 1.563171 |
| DS26-0066 | 390.672137 | 238.859981 | 1.635570 |

Both calibration arms retain observation ownership, counts and selected
publication gates. Final positions move by micrometers on 0002 and about one
meter on 0066. The latter changes six internal audit flags. The unchanged
strict verifier reports numerical histories as `not_exact` in both cases.
These observations support a useful candidate, not DS26-wide accuracy or
repeatability qualification.

Raw comparison summaries are under
`/srv/bulk/leo-dev/algo07v3-speed-lever-20261110/` in
`native-0002-fused-pair-001/summary.json` and
`native-0066-fused-pair-001/summary.json`.

## Order the next experiments by remaining native cost

Use native stage clocks rather than the original pilot's percentages.
Numerical replay already costs only 0.162 seconds on 0066 and 5.471 seconds
on 0002. The table names hypotheses, not demonstrated speedups.

| Phase | Native wall seconds, 0002 / 0066 | First alternative to evaluate | Main tradeoff or proof needed |
| --- | ---: | --- | --- |
| Predictive annotation | 6.73 / 55.81 | Test cheaper fold training after measuring its convergence. Exact recipe reuse has few hits in the saved pilot. Shared-base conditional covariance is a smaller opportunity. | Preserve held-out independence. Fewer training phase rounds are an explicit approximation requiring complete annotation and worker evaluation. |
| Inclusion and retry | 17.85 / 11.64 | Replace repeated cold Powell work with targeted feasibility restoration or continuation, followed by the full audit. | Optimizer trajectories and local minima can change. Measure gate and ownership changes. |
| Initial search | 13.41 / 37.32 | Check whether saved zero-reference first-round fits exactly replace the final zero-reference control refits. Then test paired coarse screening of branches. | Exact reuse requires whole-fit equality. Screening can miss a winning branch. |
| Conservative fit | 5.97 / 15.24 | Reuse symbolic layouts across mask changes; compare cold refits with continuation. | Numeric values must not survive a changed mask. Continuation is approximate. |
| Family policy | 8.12 / 8.16 | Check whether no-entry linear refits repeat an already saved fit. | Check result fields, objective, stops and work counts, not endpoints alone. |
| Admission | 6.48 / 19.92 | Use existing cavity/influence information to propose targets, then close the phase reference and run the full audit. | A ranking gradient is not an optimized omitted-family fit. Preserve fold independence. |
| Ranking | 4.91 / 3.53 | Apply static eligibility early; test influence shortlists before exact omission calculations. | Preserve candidate recall and account for changed audit rows. |
| Residual screen | 8.05 / 11.28 | Share candidate-independent covariance factors across predictive scores. | Do not leak full-data winners into training-fold candidate sets. |
| Additional and final repair | 0.04 / 30.11 | Share objective and constraint calculations; test derivative-assisted fitting. | Preserve explicit-family mutations, physical slacks and final orbit audits. |
| Signed and family cavity | 8.09 / 5.42 | Census duplicated phase-width/history queries and batch matching geometry queries. | Small scope. A previous geometry cache failed its representative cost screen. |

## Current experiment evidence

The saved initial-control census compares complete fit records, including types,
floating-point bits, histories and stopping records. All 18 arms match across
the eight original pilot results and the saved v4 DS26-0002 result. The provisional
v5 port reuses independent copies of those first-round records. A bounded native
DS26-0002 replay removes 54 calls and about 0.4 CPU seconds per pair of controls.
Five alternating repeats preserve the complete fit records. This is a small
component saving, not a complete-worker speed claim.

The hard-case annotation profile attributes 79.0% of annotation-child CPU to
48 fold/arm training calls and 12.9% to nomination. Covariance construction and
conditional mixture evaluation together account for 7.2%. These profiled CPU
fractions do not estimate unprofiled wall speedups.

The pure-array recipe census finds 20 potential duplicate calls among 306 planned
calls across the eight original pilots plus saved v4 DS26-0002. Only 2 of 48 calls
are potential duplicates on DS26-0066. These are planned duplicates, not proven
executed cache hits. A general training cache is not the next primary experiment.

Capture a complete hard-case annotation and compare the original five training
phase rounds with smaller explicit budgets. Retain all three folds, both arms,
48 position steps, candidates, nomination and conditional uncertainty calculations.
Report changes in all fold votes and scientific decisions before worker evaluation.
Do not combine this attempt with a precision cap or an unqualified kernel change.

Local evidence is under `/home/mouse9911/.cache/algo07v5-speed-20261112/` in
`initial-control-census-001`, `initial-controls-probe-001` and
`training-recipe-census-001`. The two checked-in census tools reproduce the saved
evidence comparisons. Full-worker and independent accuracy gates remain open.

The provisional v5 quick batch completed all three development scans. DS26-0002
matches the fixed v4 result in all non-clock scientific fields and all eight PNG
bytes. DS26-0066 similarly matches the saved full-budget native research result.
Those comparisons retain the raw clock differences and allow only named timing
fields. DS26-0102 completed, but lacks a matched saved v4 comparison in this batch.
The busy-host timings are integration evidence without alternating baseline pairs.

The bounded hard-case target-1 annotation reproduces the original five-round
annotation exactly through the probe's cloned execution path. Reducing training
to one round changes its wall time from 27.037 to 25.142 seconds and total CPU
from 33.437 to 29.241 seconds in one pair. It retains the same negative consensus,
but leaves phase-reference changes near 10 seconds instead of below 0.001 seconds.
This pair does not establish a repeatable timing gain or an accuracy frontier.

Actual work falls from 30 optimizer calls and 1,184 residual evaluations to six
calls and 722 evaluations. Two cold fits alone use 269 evaluations each and hit
the original 48-iteration budget. The next experiment tests alternative position
optimizers with all five phase rounds. The rounds probe remains available as a
rejected cost screen rather than a production budget change.

The optimizer probe now tests L-BFGS-B and trust-region least squares against the
same squared residual objective, bounds and initial position. Both alternatives
retain all five phase rounds and count every residual call, including Jacobians.
Their explicit 625-call ceiling matches the two-dimensional original GN48 worst
case. Budget exhaustion is reported separately from convergence.

The first screens cover one rejected target and one supported target on DS26-0066.
Each entry below is one complete annotation, including all folds and nomination.

| Target | GN CPU seconds | L-BFGS-B CPU seconds | Trust-region CPU seconds |
| --- | ---: | ---: | ---: |
| 1, rejected | 35.408 | 12.150 | 24.962 |
| 2, supported | 10.858 | 8.158 | Not run |

All 60 L-BFGS-B fits report convergence without exhausting a budget. Nominee
order, candidate sets, aliases, winning identities, runner-up identities and
adequacy votes remain unchanged in both annotations. Fold-training endpoints
move by at most 1.59 m. These shifts do not measure localization error. The
alternative optimizer is not enabled in the v5 worker.

This screen selects L-BFGS-B for alternating repeats and broader component checks.
It does not establish a repeatable timing ratio, complete-worker speedup or GPS
accuracy. `annotation-optimizer-screen-summary.json` retains the measurements and
the exact measured probe source. The next gates are repeated annotations, an
explicit version-bound worker policy, the quick CLI and independent qualification.

Five alternating measured pairs per target passed the component gate. On the
rejected target, median annotation CPU fell from 40.863 s to 17.024 s. The GN
range was 37.222 to 41.649 s; the L-BFGS-B range was 16.494 to 17.251 s. On the
supported target, median CPU fell from 16.766 s to 12.350 s, with ranges of
15.848 to 17.303 s and 11.522 to 12.721 s. All 300 measured candidate optimizer
calls reported SciPy success without exhausting a budget. Each annotation
retained five phase rounds and the same nominees, aliases, votes and consensus.

The rejected-target wall ranges separate, at 27.528 to 39.414 s for GN and
8.288 to 12.742 s for L-BFGS-B. The supported-target wall ranges overlap.
These measurements use three fold processes, each training both arms serially.
Production instead queues six fold/arm training tasks before prediction. The
repeat results advance the optimizer to a production-queue check; their wall
ratios do not establish a complete-worker speedup. The raw receipts and source
bindings are in `annotation-repeat-001/summary.json` under the local evidence root.

The opt-in runtime policy now has a separate request schema with a complete
descriptor. Existing v5 requests retain their original schema, run ID and GN
behavior. The runtime records SciPy termination separately from projected-gradient
stationarity. Complete-worker timing and independent GPS qualification remain open.

The production-queue integration check completed both targets. Queued GN is
bit-exact to the ordinary fold path. The runtime L-BFGS-B port retains the
nominees, aliases, votes and consensus, with all 30 optimizer calls and five
phase rounds per annotation. Residual-call counts match the earlier screen,
at 675 and 660. No candidate budget was exhausted. Only 15 of 60 candidate fits
meet the projected-gradient threshold; all report SciPy success. These are
different stopping criteria and must not be described as equal convergence.

The single queued pair uses 36.521 versus 11.765 CPU seconds on target 1 and
12.575 versus 13.518 CPU seconds on target 2. The latter is not a demonstrated
cost improvement. Repeatability of production-queue and complete-worker costs
remains open. `policy-queue-001` retains the receipts and exact measured source;
the subsequent numerical-source formatting has an identical AST. Quick and
full CLI plans select the new policy explicitly and retain the expected counts.
