# Earlier association experiments

## Objective and baseline

Find useful satellite associations during initial discovery so that the final
position needs less targeted recovery. Measure complete-worker cost and position
accuracy separately. More associations and a better frequency fit alone do not
establish better localization.

The direct baseline is the frozen algo07v5 candidate with zero RF recovery
targets, native precision and unchanged optimizer budgets. Its three optional
training/control/joint policies remain fixed. Original v3 supplies context, not
the denominator for claiming an improvement from these new changes.

The existing DS26/DS29 campaign and its frozen sources must remain unchanged.
Process liveness must be checked independently of its persisted status file.

## Ground, sketch, implement, verify

1. Trace seed generation, branch selection, phase refresh, extension, and
   successful recovery on existing DS26 development cases. Distinguish proposals
   never made, branches pruned, and proposals rejected by acceptance checks.
2. Compare two small designs for each lever. Keep independent policies so that
   each effect can be measured before testing combinations.
3. Implement opt-in policies with component-owned tests. Preserve legacy defaults
   and all existing request schemas. Bind new policies into the unreleased v5
   request, run identity, and evidence. Published v3/v4 contracts do not change.
4. Freeze source, native provider, input, configuration, references, and policies
   before numerical evaluation. Run bounded development screens first.
5. Test the surviving policies on reproducibly sampled whole scans from DS26 and
   DS29, then evaluate the selected frozen candidate on both complete inventories.
   Publish rejected experiments as well as improvements.

## Independent hypotheses

| Lever | Smallest experiment | Guardrail |
| --- | --- | --- |
| Seed diversity | Retain zero seed, then round-robin the existing ranked anchors rather than spending the short prefix on one anchor. | Same seed, branch, phase-round, and iteration budgets. |
| Branch ranking | Rank candidate association sets using their already computed calibration state rather than discarding that state before ranking. | Same number of fully fitted branches; actual fit and acceptance rules unchanged. |
| Earlier association | Investigate one calibrated proposal pass for families absent from the chosen initial branch. | Do not duplicate existing discovery/extension passes or relax acceptance merely to increase counts. |
| Residual recovery cost | Share training work only for exactly identical training masks and model inputs. | Zero-target baseline does not execute this work, so this cannot improve that baseline directly. |

Seed diversity has two candidate designs: anchor round-robin and calibrated-state
distance selection. Round-robin is the initial choice because it requires no new
distance scaling. The distance variant is deferred until evidence shows redundant
anchors defeat the simpler approach.

Earlier association and recovery caching require a demonstrated gap before
implementation. A rejected or redundant hypothesis is a valid result, not a
reason to add another unconditional fit.

## Evaluation protocol

- Start with DS26-0002, DS26-0066, and DS26-0102 as development cases. Their
  outcomes are already known and cannot establish generalization.
- Compare legacy, diversity only, ranking only, then their combination if the
  individual screens justify it. Keep recovery at zero in every direct pair.
- Use fixed seeds and whole-scan groups for qualification assignments. Mark all
  previously inspected scans as development. DS29 is a chronological corpus,
  not a randomized holdout; sample groups within it without inspecting outcomes.
- Freeze the policy before DS29 evaluation. If DS29 outcomes inform a revision,
  those scans become development and require fresh qualification groups.
- Keep native observations, causal TLEs, priors, search region, scientific
  deadlines, precision, and all unrelated policies matched.
- Run matched c=0 and fitted-c arms. GPS/operator coordinates enter evaluation
  only. DS29's operator reference is not surveyed GNSS truth.
- Include every inventory member in full reports. Missing, failed, timed-out,
  and incomplete cases remain visible and never earn speed credit.
- Report complete-worker wall and CPU time; stage work and native calls;
  position error median/p95/max and paired deltas; association ownership changes;
  frequency score and RMS separately. Scores on different observations are not
  evidence of improved matched-observation fit.
- Alternate baseline/candidate order. Concurrent host measurements are
  descriptive. Repeat a fixed availability-selected sample five times per side
  serially before claiming repeatable latency improvement.
- Select a speed/accuracy frontier, not an accuracy threshold invented after
  observing results. Discuss material tail regressions explicitly.

## Ownership and throughput checkpoint

Sol xhigh agents own disjoint scopes: seed policy and tests; branch/early-pass
design; v5 request/CLI wiring and tests; and the new evaluation driver. The root
owns initial-search integration, this decision trail, and final review. Use
standard service. No new RF collection or QNAP mutations are authorized.

New experiment artifacts live under
`/srv/bulk/leo-dev/initial-discovery-20261113`. The existing campaign owns its
original directory. Freeze candidate copies before running them so later edits
cannot invalidate an active experiment. Limit numerical concurrency according to
actual host load; coding and unit tests may proceed while campaigns are active.

Completion requires tested implementation, real DS26/DS29 evidence, reproducible
CLI commands, and an explicit decision for each hypothesis. A queued full run is
reported as pending, never as completed evaluation.

## Execution record

- Legacy initial-search regression tests pass after adding the optional ranking
  policy: 15 tests. The new warm ranking uses the node's clipped phase reference;
  selected branches still start cold and receive all original fits.
- Saved evidence identifies a useful counterexample on DS26-0102. The recovered
  NORAD 68106 family was absent from the initial winner. Other recovered targets
  were already initially owned, so not all recovery work is missed discovery.
  A missing family on DS26-0066 failed predictive checks. Earlier proposals must
  therefore retain acceptance checks.
- The original campaign's status file was stale. There were no live workers,
  and four worker attempts had partial outputs without reports. Those outputs,
  logs, and receipts were preserved under the new experiment's
  `original-campaign-recovery/20261113T150718Z/manifest.json`. A complete staged
  candidate was retained for resume. No scientific failure was inferred from
  interruption and no frozen code or protocol changed.
- The original campaign resumed under the user systemd unit
  `leo-ds26-ds29-evaluation-20261113.service` at 2026-11-13T15:07:24Z.
- The opt-in seed and ranking policies are implemented. Explicit policy values
  use schema 6 of unreleased v5, with request identity, evidence, and resume
  checks. Omitted policies retain schemas 1 through 5. Independent review found
  no blocking implementation defect; the wiring regression set passed 335 tests
  and the final operations set passed 72.
- The final candidate source is `frozen-candidate-002`, with `native-002` in the
  experiment root. The unused candidate 001 remains preserved. Numerical native
  code and precision are unchanged; the source differs in initial discovery and
  explicit policy wiring.
- The proposed extra initial `explore` pass is rejected for this round. On saved
  DS26-0102, the bounded probe reproduced the original initial objective exactly,
  then produced identical labels and aliases with zero support for NORAD 68106.
  Its target track is absent from the raw-curved proposal set. The pass took
  1.43 seconds in this single diagnostic run, not a speed benchmark. Evidence is
  `early-association-probe/probe-0102-001/result.json` in the experiment root.
  Supporting weaker tracks requires a different proposal mechanism and fresh
  acceptance evidence; repeating the existing pass does not address the miss.
- Commit `5254d2f35` binds the implemented policies and their tests. The first
  complete paired worker, seed-only DS26-0102, passed public-store validation:
  c0 position error 942.645 to 872.348 m; fitted-c 936.345 to 850.464 m.
  Frequency RMS increased by 0.654 and 1.062 Hz, respectively. Both arms lost
  two associated points; satellite count increased from 21 to 22. Different
  ownership means the lower total objective is not a matched-data fit claim.
  CPU was 233.619 versus 197.991 seconds and wall 190.136 versus 160.243 seconds.
  This single contended pair does not establish repeatable speed improvement.
  Validated evidence lives at
  `/home/mouse9911/.cache/initial-discovery-20261113/dev-seed-only-0102-001`.
- The initial-only DS26-0066 legacy replay reproduced the entire saved initial
  result exactly before testing policies. The probe uses the genuine-false
  original context, both arms, all three branches and all five fitting rounds.
  Intermittent bulk filesystem stalls required an explicitly hash-verified NVMe
  source mirror and a real native rebuild with matching numerical bytes and
  provider settings; its physical paths are bound in the probe plan.
- Full paired output is estimated at 116 GB, exceeding current root free space.
  The new driver validates completed publications then archives verified bytes
  outside worker timing, preserving original absolute paths through symlinks.
  Full evaluation remains pending policy selection and archive-driver review.
- The six bounded initial-only runs completed on DS26-0002 and DS26-0066:
  legacy replay, seed-only, and ranking-only for each. Both legacy replays
  reproduced the entire saved initial result exactly. Seed-only preserved all
  scientific results on both scans. Ranking preserved every per-signature arm
  result and winner, but swapped the two losing branches; it added four and six
  native calls respectively. No native fallback occurred. These are component
  comparisons, not whole-worker speed or position-accuracy measurements.
- Seed-only is selected for the frozen DS29 then DS26 quick qualification,
  before inspecting those qualification outcomes. Ranking-only remains a
  development alternative; combined policies are not justified by these tests.
  The known 68106 miss is still absent from both initial and final DS26-0102
  output. Seed diversity added two initially accepted tracks with other NORADs;
  the final additional identity is 101018. Do not describe this as resolving
  the known weak-track discovery failure.
- Replay tooling is committed as `f6131fe81`; the evaluation/archive driver as
  `705e73ebd`. The driver passed 44 owned tests and independent review of the
  archive crash windows and actual numerical request binding. The first 0102
  pair also passed the strengthened request validator. Frozen runner 002 is
  superseded by 003 before qualification launch; active quick runner 001 and
  completed evidence are preserved.
- The remaining DS26 seed-only whole-worker pairs completed and passed the
  stronger request validator. DS26-0002 and DS26-0066 preserve all reported
  scientific metrics and point owners exactly. CPU increased from 167.873 to
  178.757 seconds and from 293.940 to 306.816 seconds respectively; these single
  contended runs demonstrate no speed gain. The first DS29 qualification worker
  (0336 baseline) started at 2026-11-13T15:42:06Z under runner 003.
- DS29-0005 was explicitly marked development before a bounded component test;
  it is outside the four frozen DS29 qualification groups. Its legacy replay
  reproduced the saved initial result exactly. Seed diversity expanded unique
  proposals from five to six and replaced one losing fitted branch, while the
  complete winning arm payloads remained exact. Warm ranking retained all three
  branches and exact arm payloads, adding five native calls. Neither policy
  changed winning endpoints, objectives, or owners. All 90 fits completed with
  no native fallback; this is not a full-worker accuracy or timing result.
  Evidence is `component-screen/DS29-0005-summary.json` in the experiment root.
- The first frozen DS29 qualification pair, 0336, completed public validation
  and archival. Both arms preserve position errors (1.499930/1.423120 km),
  frequency metrics, all 2973 associated points, and owners exactly. CPU rose
  from 182.328 to 230.236 seconds and wall from 162.380 to 204.628 seconds in
  this single contended pair. Native calls were 4103 versus 4104, with no
  fallback. This material observed timing regression needs fresh repetitions
  before attributing its size to policy. No general speed benefit is established.
- Historical-control full evaluation is committed in `588983b7d`. It validates
  original fast-v5 publications without rewriting them, separates candidate
  coverage from pending paired coverage, and disables timing before comparison.
  The separately frozen runner 004 follows qualification under the same lane
  lock. Full population results remain pending; both policies remain opt-in.

## Continuation checkpoint: 2026-11-13 16:34 UTC

The original v3 versus fast-v5 campaign has 40 complete DS26 pairs and 41
complete DS29 pairs. Aggregate worker wall ratios are 2.697x and 3.143x;
median per-pair ratios are 2.210x and 2.470x. Four DS26 and two DS29 attempts
failed on both sides. These are partial contended results, not full-population
or serial-repeat qualification. Fast v5 is still the unchanged reference for
the separate seed experiment.

Median paired position-error change is approximately zero, but tails matter:
DS29-0399 loses 56 points and changes c0 error from 377.471 to 1269.409 m,
and fitted-c from 466.076 to 1311.255 m. This recording is now development for
any future policy informed by this diagnosis; GPS must never become an inference
trigger. Investigate the missing evidence and a radio-only need-for-recovery
indicator without changing the active frozen policies.

All four DS29 seed-qualification pairs completed. Three have identical position
errors; 0412 improves by 1.705/2.562 m with one fewer point. Aggregate worker
wall is 2.36% lower and CPU 2.79% lower, with large opposing per-case timing
changes. This does not establish repeatable speed improvement.

DS26 qualification has shared failures: 0156 raises orbit phase interpolation
out-of-range; 0108 ends with final propagation_fallback. The latter also occurs
in the original v3 and fast-v5 campaign. Preserve these failed outcomes, with
no accuracy or speed credit. A separately reviewed continuation gate may admit
exactly documented matched scientific failures while rejecting input drift,
contract errors, candidate-only failures and incomplete coverage. Do not bypass
the orbit or propagation safety guards to make the evaluations complete.

Follow-up diagnosis separates two mechanisms. On DS26-0102, the weak target
track has 33 points over 23.738 seconds and raw detrended RMS 148.950 Hz,
below the frozen 250 Hz curved-track threshold. NORAD 68106 is already in
the 1420-candidate initial catalogue. A radio-only filter for wholly unowned,
noncurved tracks with sufficient support leaves two targets; this track ranks
first. A bounded proposal-only probe will test the existing nomination routine
without changing calibration membership or authorizing position inclusion.
The saved later RF-qualified label is conditional evidence: the target still
has zero published ownership in both arms.

On DS29-0399 the lost track was correctly nominated as NORAD 66466, but its
whole-track residual failed the initial noise gates. The original conditional
timing-gap stage eventually admitted 56 of its 57 points. Existing timing-only
gap rules identify exactly this track among the five remaining candidates:
56 points span 54.235 seconds, with an isolated final point after a 6.022-second
gap. Investigate direct admission of that component with existing scientific
checks. Its native-v5 cost is unmeasured; original recovery timings cannot
establish the speed of this proposed shortcut.

The bounded weak-track nomination probe completed successfully. It selected
two tracks using only radio support and searched all 1420 initial catalogue
candidates. NORAD 68106 ranked first among retained coarse offers for the
target (cost 7.183; next offer 3437.702). Both initial arm scores and states
replayed exactly. Nomination took 2.461 seconds, total probe stage 11.570
seconds, with eight native calls, no fallbacks and no optimizer fits. These
are component timings and proposal evidence, not a worker speedup or accepted
identity. Seven owned tests and independent review passed; the combined
nomination checks passed 24 tests. Tool commit: `ebc78932b`.

Evidence is preserved under
`/srv/bulk/leo-dev/initial-discovery-20261113/weak-track-68106/`.
Next, use the existing independent annotation folds at the genuine-previous
recovery checkpoint. Each fold must refit calibration excluding held blocks
and guards, then independently nominate from the full causal bank. Never reuse
the full-data nominee as a training-fold shortlist or use the saved full-data
calibration as independent training evidence.

Qualification finished at approximately 16:46 UTC: DS29 has four completed
pairs; DS26 has two completed pairs and the two documented shared failures.
DS26-0255 is scientifically exact. DS26-0317 adds 62 associated points but
worsens position error by 51.36 m (c0) and 58.15 m (fitted-c), while frequency
RMS rises by 0.842/2.432 Hz. More associated points do not establish better
localization. Seed diversity remains opt-in and is not an accuracy promotion.

Reviewed continuation service
`leo-initial-discovery-full-sequence-005.service` is active and queued behind
the existing ranking development sequence and retirement of coordinator 004.
It uses separately frozen runner 005 and plans, preserves the two failures,
and validates their actual requests and public evidence before continuation.
The full DS26/DS29 candidate evaluation uses historical fast-v5 controls for
accuracy only; it cannot produce a fresh paired timing claim. The runner fixes
JSON tuple/list receipt equivalence (`f7b17bd4d`); active numerical sources,
scientific policies and budgets are unchanged. No full-population result is
available yet.
