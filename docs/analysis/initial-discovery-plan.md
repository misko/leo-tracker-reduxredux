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
