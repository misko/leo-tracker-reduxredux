# Algo07v4 baseline and algo07v5 goal

All three runtime joint-policy quick workers now pass complete publication
validation. DS26-0002 and 0066 execute no joint experiment and retain all
selected science, eight PNGs each, and native/training/control work counts
exactly. Only 16/54 named audit clocks differ. Combined with the 0102 gate,
all 24 PNGs and all selected results match the prior current-v5 references.
Quick GPS error median/p95/max are 0.908834/1.210361/1.243864 km for c0
and 0.874911/1.183293/1.217558 km for fitted-c, unchanged by this policy.
These three development cases are not independent DS26 qualification.

The new 0002 worker records 176.104485 wall / 229.055025 CPU seconds,
and 0066 records 289.690773 / 409.512588. Their physical work is unchanged,
yet their timings differ from earlier controls. This demonstrates why
separated timings cannot establish the new schedule's causal worker gain.
The next timing pair runs current final-policy v5 before frozen v3 on 0102,
reversing the earlier order. Alternating repeats and independent qualification
remain required. See `joint-schedule-quick-summary-001.json` and
`worker-joint-schedule-remaining-001/validation/` under the evidence cache.

First complete-worker integration of the joint policy passes on DS26-0102.
Both predictive and numerical recovery omit their factorized pair after
the full control/joint audits exclude numerical retry. Native calls drop
15659 to 15006. Selected evidence, GPS errors, frequency scores and all
eight PNGs match the prior current-v5 worker exactly. After removing only
the eight explicitly omitted stage records and four corresponding
numerical receipts, the remaining 31 audit differences are clocks.
Annotation work remains 210 completed fits / 6018 physical residuals /
eight GN fallbacks; control work remains six requests, five computed and
one reused. Two joint experiments complete, both eligible, with no
scheduling failures or unfinished work.

Observed complete-worker wall/CPU times are 401.607870 / 643.249736 seconds
before and 364.113634 / 564.538212 after. This separated pair is not timing
qualification and must not be combined with an earlier v3 timing to claim
2x. Real runtime component replay also passes through the original
controller/factory port, with only the declared stage omission. Remaining
quick controls and alternating repeats are next; independent DS26
qualification remains open. Evidence is under
`~/.cache/algo07v5-speed-20261112/worker-joint-schedule-0102-001/`, including
`validation.json` and every raw/normalized audit difference.

The conditional joint schedule is now wired as the independent opt-in
`defer-factorized-unless-retry-v1` policy. Schema4 requests bind it into the
run identity; schema1/2/3 remain unchanged. A narrow factory port reaches
predictive and numerical recovery, and replay verifies the checkpoint's
policy before consuming saved stages. Operations owns native-manifest
validation and reports actual completed, failed, omitted and unfinished
experiments. Unknown callbacks and numerical policies retain the original
schedule. All 1558 relevant checks pass, including paired selection and
per-stage receipt comparisons. Runtime component and complete-worker
qualification are still required; this integration is not a measured new
worker speedup.

Latest continuation: a fresh matched DS26-0102 pair completed at
753.920414 seconds / 1369.053036 CPU seconds for frozen v3 and
401.607870 / 643.249736 for current v5 with both opt-in policies. This is
1.877255x wall and 2.128338x CPU in one adjacent pair, below the required
2x wall target. Host CPU pressure fell during the baseline. Reverse-order
repeats and independent qualification remain open. Both arms retain all
3471 owners; GPS-error differences are below 0.02 mm. Current v5 repeats
its previous complete selected result, eight PNGs and all work counts
exactly, with only 31 audit clocks changing. See
`~/.cache/algo07v5-speed-20261112/worker-repeat-0102-001/validation.json`
and its shared-CLI comparison.

A bounded joint experiment rejects factorized-endpoint warm initialization:
the complete fit/audit pair increases from 54.495700 to 62.178628 wall
seconds and 106.838267 to 109.130047 CPU seconds. Objective evaluations
change from 156/153 to 138/204 across the arms, introducing a fitted-c
optimizer failure. No warm-start runtime policy is enabled.

The next exact-work hypothesis is to defer factorized fits until control
and joint audits show they are necessary for numerical retry. On 0102,
joint phase-resolution failure already excludes that retry. A replay of
the original control and joint fits/audits preserves every remaining
field bit for bit and both decisions, while omitting factorized work:
74.943440 to 60.282623 wall seconds and 140.535722 to 114.628989 CPU
seconds for this component. All original optimizer and phase budgets
remain intact. The scope excludes already paid probe/preparation work;
this is not a worker ratio or independent qualification. Tools
`probe_algo07v5_joint_start.py` and `probe_algo07v5_joint_schedule.py`
retain the negative and positive screens. Their 27 owned tests include
4096 acceptance/retry combinations against the original decision rule.
Next is an explicit worker policy with complete-work accounting and
matched predictive/numerical checkpoint binding, followed by the shared
CLI quick evaluation. Unknown or stateful callbacks need the original
schedule; numerical replay still requires its own execution validation.

The public-work census also limits the opportunity from dropping GN
fallback: it accounts for only 3.01%, 4.59% and 6.19% of annotation
residual evaluations on 0066, 0102 and 0002. These are work shares, not
wall-time shares. Keep fallback while pursuing the larger scheduling
opportunity. No full batch or new RF collection ran in this continuation.

Algo07v4 preserves the full-budget native solver as a separately identified
implementation. Algo07v3 keeps its original solver. The provisional algo07v5
runtime is registered for evaluation with an explicit initial-control reuse
policy. It has not met the speed target or completed independent DS26 qualification.

## Proposed slash goal

```text
/goal Develop algo07v5 to run at least 2x faster end to end than frozen algo07v3
on DS26. Keep published algo07v4 fixed as the baseline and rollback; another
2x over v4 is a stretch target. Prefer removing repeated work, then measure
explicit speed versus accuracy tradeoffs before choosing an approximation.

Use the pinned environment and tools/evaluate_algo07.py:
- Quick: run --profile quick --version algo07v5 for DS26-0002/0066/0102.
- Full: plan --profile full, then run --profile full, with the same version.
- Compare: compare --baseline BASELINE/report.json --candidate CANDIDATE/report.json.
Follow docs/how-to/evaluate-algo07.md for --snapshot, checkout-bound
--native-manifest and fresh --output arguments. Keep experimental policies
explicit. Run bounded component checks before quick workers; qualify finalists
on the independent remaining scans. Retain all 159 expected DS26 members,
including missing DS26-0172, and report every failure and timeout.

Measure complete-worker wall/CPU time, phase costs and actual work. Confirm
timing with alternating repeats. The primary speed ratio is baseline total
wall time / candidate total wall time over matched complete available scans;
also report per-scan ratios and tails. Incomplete work earns no speedup.

Keep c=0 and fitted-c comparisons matched in observations, candidates, priors
and budgets. Report GPS median/p95/max and paired outliers separately from
frequency fit, ownership and audit changes. GPS is evaluation-only. Preserve
negative results and one change per experiment. The goal is achieved only
after independent qualification meets both the speed target and an explicitly
chosen accuracy budget; otherwise report the measured frontier and bottleneck.
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

The first complete-worker L-BFGS-B attempt on DS26-0066 failed in target 0
annotation. It produced no scientific result and earns no timing ratio. Fixed
v4 completed in the same experiment. A bounded replay traced the failure to
an abnormal SciPy return whose restored parameters and reported score disagree;
the recorded score at those exact parameters is consistent. The repair retains
the raw status and score and still reports the primary fit as unsuccessful.

The next candidate, `lbfgsb-gn-fallback-full5-v1`, reruns an unsuccessful
primary fit with the original GN48 solver from the original phase start.
Its explicit worst-case budget is 625 primary plus 625 reference residual
calls. Both attempts, failures and physical work remain visible. This policy
passed bounded production-queue checks on targets 0, 1 and 2. Every annotation
completed all 30 phase results, with 745, 675 and 660 residual calls. Target 0
used one GN fallback; the other targets used none. No budget was exhausted.
Nominees, aliases, votes and consensus remain unchanged in all three checks.

The single-pair annotation CPU costs were 11.583 to 10.290 seconds, 34.518 to
11.274 seconds and 11.666 to 8.440 seconds respectively. Target 0 wall time
increased, from 4.146 to 5.400 seconds. These component measurements advance
the candidate to another complete-worker attempt; they establish neither a
stable worker speedup nor GPS accuracy. Local evidence is in
`worker-policy-0066-001`, `policy-target0-corrected-001` and
`policy-fallback-queue-001` under the evidence root above. The latter archives
the exact measured source before an AST-identical probe line wrap.

The robust candidate then completed DS26-0066 through the shared evaluation CLI.
Its entire selected result and all eight PNGs match fixed v4 exactly. Both arms
retain GPS errors of 1.243864 km and 1.217558 km, respectively, with identical
frequency scores, residual RMS and ownership. The audit differs in 54 timing
fields and 168 stored margin fields representing 56 distinct predictive margin
values; the largest absolute margin change is 0.010126. Every other audit field
matches. Five unsuccessful primary fits completed full GN fallback. All 240
phase fits completed, with 245 optimizer attempts, 6,016 residual evaluations,
four recorded-score corrections and no exhausted budgets.

One worker comparison uses 475.988 versus 307.756 CPU seconds and 318.030 versus
217.209 wall seconds. The fixed-v4 baseline was saved earlier, not alternated
with this retry. Unchanged native preparation also fell from 14.179 to 10.550
wall seconds. The overall 1.464 wall ratio therefore remains an integration
observation requiring alternating repeats; do not multiply it by historical
v3/v4 ratios to claim the 2x goal. Raw reports, work validation and exhaustive
selected/audit differences are in `worker-fallback-0066-001`, with paired
metrics in `worker-fallback-0066-001-comparison`. Next are the other quick
cases, alternating complete-worker repeats and independent qualification.

The remaining quick cases also completed. DS26-0002 and DS26-0102 match
their saved default-GN v5 references in the entire selected result and all
eight PNGs; their audits differ only in named clocks and annotation margins.
The respective maximum margin changes are 0.025932 and 0.024847. All 60 and
210 phase fits completed, including 10 and eight full GN fallbacks, without
exhausted budgets. Thus all three development cases preserve their selected
results. This does not establish independent DS26 accuracy.

Timing observations remain mixed. DS26-0002 used 251.383 CPU seconds versus
250.624 in its saved reference; DS26-0102 used 857.910 versus 763.543. Those
references had 900-second deadlines and an earlier runtime, whereas the new
screen used 1,200 seconds. `quick-fallback-remaining-001/validation` records
scientific comparisons without timing ratios. The raw clocks motivate fresh
comparisons, not a universal speedup claim.

A fresh adjacent v3/v5 pair on DS26-0066 uses identical frozen inputs,
1,200-second deadlines, CPU affinity and BLAS settings. Frozen v3 completed
in 428.954 wall / 708.033 CPU seconds; v5 completed in 270.927 wall / 368.605
CPU seconds. The observed ratios are 1.583 wall and 1.921 CPU. Ownership
remains unchanged; GPS errors differ by about one meter, as in the native
baseline comparison. This directly measured wall ratio is below the 2x goal
and still needs reverse-order repeats. `worker-repeat-0066-001` retains the
commands, source bindings, complete reports and shared-CLI comparison.

Initial search still costs 34.836 seconds in that candidate. The next bounded
lever compares the complete initial-search optimizer against untouched GN,
then tests L-BFGS-B with all branches and five phase rounds. No initial-search
optimizer change is enabled in the worker. A read-only phase census also
finds expensive late L-BFGS-B fits on DS26-0002; choosing GN for warm later
rounds is a separate hypothesis, not a measured hybrid policy.

The complete initial-search screen rejected L-BFGS-B. The untouched GN oracle
used 40.154 wall / 56.440 CPU seconds; cloned GN used 39.674 / 56.327 and
matched the entire oracle result bit for bit. Both used 30 phase fits and
1,366 residual evaluations, including one original iteration-budget stop.
L-BFGS-B used 100.100 wall / 120.765 CPU seconds and 2,410 residual evaluations.
Only 27 of 30 fits reported convergence, with one exhausted budget. It retained
the branch winner and nominations but changed some branch-level acceptance
and graph-association decisions. This is a rejected component cost screen,
not a measured GPS tradeoff. No initial optimizer extension is enabled.
`initial-optimizer-0066-001` retains the qualified oracle and both comparisons.

The next exact-work hypothesis is the inclusion-control cache bypass: the scan
now stores a callable backend, while cache eligibility rejects callable scan
fields. A read-only audit proved the bypass, but reuse and savings remain
unmeasured. First census prospective keys and independently recompute any
colliding controls. Keep all scientific fingerprints and unknown-callback
rejections; do not enable cache reuse until complete results match.

The observational control census now reproduces complete saved native recovery
on DS26-0002 and DS26-0066. It fingerprints geometry and every mutable scientific
field, replacing only the known backend object with its bound manifest digest.
No control is reused. The 0002 case has three different configurations and no
duplicate keys; its controls cost 4.543 seconds in total. The 0066 case has four
controls with one key, and all three independently recomputed duplicates match
the first complete c0/fitted-c pair. Their combined compute cost is 9.311 wall /
17.727 CPU seconds. Keying all four controls costs 0.882 seconds.

These costs identify a small exact-work opportunity, not a measured worker gain.
The next gate enables reuse only in the diagnostic replay, preserving complete
recovery equality before adding a runtime policy. The new checked probe is
`tools/probe_algo07v5_control_census.py`; raw evidence is in
`control-census-0002-001` and `control-census-0066-001`. Its 81 focused checks
cover complete-pair comparisons, copy isolation, unknown callback rejection,
scientific fingerprints, unchanged controller behavior and failure handling.

Explicit diagnostic reuse now passes complete recovery equality on 0066,
including the current L-BFGS-B/GN fallback candidate. It replaces three control
computations with independent copies and removes 759 native solver calls. The
keys and complete control-pair fingerprints also match between GN and fallback
training configurations. Unknown callbacks remain ineligible; geometry stays
in the fingerprint. No scientific budget is reduced.

| Diagnostic recovery | Wall seconds | CPU seconds | Native calls |
| --- | ---: | ---: | ---: |
| GN, uncached census before | 102.617 | 232.020 | 9,997 |
| GN, explicit reuse | 86.890 | 200.470 | 9,238 |
| GN, uncached census after | 92.237 | 170.099 | 9,997 |
| Current fallback training, explicit reuse | 64.480 | 118.678 | 7,191 |

The later uncached run uses the same probe version as the reuse run. All four
complete recovery audits match their saved references. Wall observations favor
reuse, but CPU variation prevents a stable timing-ratio claim. The control
computations alone cost 8.562 to 9.311 wall seconds in the uncached runs;
reuse keying costs 0.646 to 0.949 seconds and copying at most 0.016 seconds.
These are component observations, not complete-worker results or a 2x claim.

The probe's `--reuse` option is explicit and off by default. Its expanded 84
focused checks pass. Raw observations are in `control-reuse-screen-summary-001.json`
and `control-reuse-fallback-0066-001`. Next, add a separately identified opt-in
v5 runtime policy and work accounting, preserving old requests and the fixed
v4 implementation, then evaluate complete workers through the shared CLI.

The runtime implementation now has the separate opt-in policy
`native-complete-controls-v1`, selected with `--inclusion-control-policy` in
the shared evaluator. Schema 3 binds this independently of annotation training.
Legacy schema-1/2 request descriptors, run IDs and resume behavior remain stable.
The pure cache receives a narrow backend-identity port; operations own manifest
validation and work accounting. Each recovery invocation gets a fresh cache.
Numerical replay checks checkpoint policy compatibility before reusing stages.

The common runtime suite passed 1,492 tests. An additional focused 73-test check
includes the newly added real-factory probe route. The registered factory then
reproduced the current 0066 fallback candidate's entire recovery audit through
its actual port: four requests, one computed pair, three reused pairs and no
failures or incomplete work. This is a component gate; the next check is a
complete-worker CLI run with both explicit policies. Source and receipts are
under `control-runtime-replay-0066-001`, with quick/full request plans in
`control-runtime-plan-quick-001` and `control-runtime-plan-full-001`. Full plans
still retain 159 expected, 158 available and missing DS26-0172.

The complete schema-3 worker passed DS26-0066. Its entire selected result and
all eight PNGs match the uncached fallback candidate exactly. All non-clock
audit fields match; only 54 named timing fields differ. GPS error, frequency
score, residual RMS and observation ownership are unchanged in both arms.
Control accounting records four requests, one computed pair and three reuses,
with no failures or incomplete work. Numerical replay creates a separate empty
cache invocation. Annotation work remains 240 completed phase fits, 6,016
residual evaluations and five full GN fallbacks. Native calls fall exactly
from 13,198 to 12,439.

This worker uses 245.497 wall / 326.980 CPU seconds, versus 270.927 / 368.605
in the saved uncached candidate. Those runs were separated in time, so their
1.104 wall ratio is an integration observation. The 2x target remains unproven.
Raw reports and exhaustive public-store comparisons are in
`worker-control-reuse-0066-001` and `worker-control-reuse-0066-001-comparison`.
Next are the other two quick cases and fresh alternating timing qualification.

The cache-enabled workers also completed DS26-0002 and DS26-0102. Both match
the uncached candidate in the entire selected result and all eight PNGs. Audits
differ only in 16 and 31 named clock fields; no margin or ownership changes
occur. Annotation work is unchanged. The cache remains ineligible for stateful
numerical replay, as intended.

| Scan | Computed control pairs | Reused pairs | Native calls before / after |
| --- | ---: | ---: | ---: |
| DS26-0002 | 4 | 0 | 7,657 / 7,657 |
| DS26-0066 | 1 | 3 | 13,198 / 12,439 |
| DS26-0102 | 5 | 1 | 15,880 / 15,659 |

The new 0002 worker used 182.431 wall / 251.226 CPU seconds. The 0102 worker
used 393.052 / 612.812 seconds. These runs were separated from their uncached
references; large timing changes cannot be attributed to the small call-count
reduction alone. Full comparisons and work validation are in
`worker-control-reuse-remaining-001` and its `-comparison` directory.

A synthetic fault test proved that a cache identity exception could be caught
as an ALGO02 scientific fallback inside the recovery controller. Cache integrity
failures now bypass scientific rejection handlers and the v5 CLI records them
as failed work. Regression tests cover changed identities and incomplete pairs;
the expanded common suite passes 1,497 tests. None of these faults occurred in
the three healthy worker checks. The change affects failure handling only.

An offline radio-only census found no quick-case opportunity to skip a joint
trial by its added-point ceiling. On 0102, the possible joint pair can add 67
points versus the incumbent's 34, so it can still win. First-fold rejection
suggests another possible saving, but later numerical rescue must be considered
before claiming decision equivalence. Neither pruning policy is enabled.
Before further optimization, measure frozen v3 against the current v5 on the
heavier 0102 case. A later candidate lever is to initialize costly joint fits
from the already-computed same-arm factorized fit, retaining full joint
objectives, phase rounds and audits. That alternative has not been evaluated.
