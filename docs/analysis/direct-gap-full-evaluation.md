# Frozen timing-gap evaluation on DS26 and DS29

The user authorized the full evaluation after the
[bounded investigation](algo07v5-bounded-conclusion.md). The question is how often
`direct-timing-gap-v1` buys position accuracy at a useful computational cost.
The weak-track inclusion experiment remains stopped.

## Comparison and evidence

The candidate keeps the frozen timing-gap policy, legacy initial discovery,
zero ordinary recovery targets, and the existing numerical and acceptance
budgets. It runs both matched calibration arms, `c0` and `fitted_c`. Evaluation
coordinates stay outside inference. DS29 coordinates are operator roof
references rather than surveyed positions.

The control is the original campaign's frozen fast-v5 candidate. Each imported
report keeps its actual source, evaluator, native manifest, request, run identity,
publication paths, and process receipt. Historical controls support paired
accuracy and work comparisons. They do not support paired timing arithmetic.

The source review found nine changed bound source files between the old control
and the frozen timing-gap worker. Those changes add opt-in discovery and gap
behavior. The legacy paths remain unchanged in the reviewed branches. Native
binary, C source, wrapper, and BLAS provider hashes match. The old and fresh
no-gap controls have identical scientific arm dictionaries on DS26-0002,
DS26-0263, and DS29-0399. This is evidence for reuse, not proof of equivalence
on every recording. Both source bindings remain explicit in every manifest.

The frozen cohorts contain 159 DS26 members and 615 DS29 members. One DS26
input and three DS29 inputs are missing. Retain all 774 members in coverage
reports. Run at most one new candidate worker for each available member.
The full corpus includes development recordings and previously inspected
outcomes. It is a whole-corpus evaluation, not an independent holdout.

## Existing campaign summaries

The original campaign refreshes its public-store report after bulk execution
and serial repeats. Its older live reports therefore contain only two pairs.
The producer snapshots taken at 02:04 UTC on November 14 contain 99 complete
DS26 accuracy pairs and 113 DS29 pairs. Those snapshots preserve current
coverage, both calibration arms, accuracy tails, and failure counts.

These snapshots are producer summaries, not independent public-store audits.
The evidence-only public validator was stopped after a ten-minute bounded
attempt. It has no partial cache and checks several files that the running
campaign updates independently. Preserve that unfinished audit separately from
the scientific campaign's worker outcomes.

The snapshot script and reports remain under
`/srv/bulk/leo-dev/ds26-ds29-evaluation-20261113/reporting/`.
The script is `snapshot_producer_aggregate.py`. The report directories are
`ds26-producer-snapshot-20261114-0204` and
`ds29-producer-snapshot-20261114-0204`. Re-run the existing
`summarize_cohort.py` after publication stops for independent validation.
The new timing-gap collector independently validates its own historical
fast-v5 controls through their public stores.

## Execution and stopping rules

Store the runner, manifests, staging, archives, reports, and coordinator state
under `/srv/bulk/leo-dev/initial-discovery-20261114/direct-gap-full-001`.
The scientific worker remains frozen at
`/srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-worker-001`.

Use one worker on CPU 21, one BLAS thread, and a 2,400-second per-worker cap.
Run the coordinator at reduced scheduling priority. Preserve the existing
original-v3 and seed-policy campaigns. All measurements on this busy host remain
ineligible as headline speed benchmarks.

The coordinator runs DS26 and then DS29. It imports newly available controls and
updates evidence-only reports. If controls remain pending, it checks the
original campaign every 300 seconds. Candidate coverage, paired coverage, and
scientific success are separate results. A terminal failed or timed-out worker
counts toward attempted coverage and remains a failed scientific outcome.

Stop on a changed frozen binding, invalid public evidence, resource admission
failure, or coordinator error. Retain interrupted workers for inspection.
Never silently retry an attempted numerical worker. An unavailable historical
control remains pending until the original campaign publishes it or stops.

## Decision after coverage is known

Report trigger frequency, identity and fit rejections, accepted additions, exact
owner changes, position-error distributions and tails, frequency evidence,
candidate stage costs, native work, and all unsuccessful outcomes. Report both
calibration arms separately. Do not infer better position accuracy from a better
frequency fit.

The collector distinguishes no trigger, identity rejection, fit rejection,
stage failure, acceptance, and inconclusive trials. Candidate stage costs include
every completed candidate, even when its control is pending or failed. Paired
accuracy and native call deltas require two complete roles. Position change
counts use a one-meter tie threshold. Distributions include p90 and p95 and
state their measured and planned recording counts.

Select any optimization from the recurring measured cost. Annotation currently
takes about 17 to 35 seconds on the two triggered recordings. Inclusion takes
about 24 to 31 seconds. These observations do not establish population cost.
The existing control cache excludes conditional satellite refresh, so control
reuse needs a numerical equivalence proof before implementation. Moving the
millisecond eligibility check earlier offers little demonstrated benefit.

After choosing a policy, use fresh matched timing runs against original v3 and
fast-v5. Keep those timing results separate from historical accuracy comparisons.
The earlier speed estimates and the bounded gap-stage cost cannot be combined
into a new measured end-to-end speedup.

## Launch and verification record

The persistent user unit is `leo-direct-gap-full-001.service`. Its invocation
ID is `99abbc07710a46469d03f6ca3a7ad038`. The exact argument vector and launch
result are in the study's `launch-receipt.json`. The freeze receipt is
`freeze.json`, SHA256
`5ee923aff13a25ec7068742eae56f9a50e9042901bfab6f70447c8caeab0ab18`.
The two manifest hashes are:

- DS26, `11262f99c765edccc6df3a507aee57db961bd743adfb257cedbe1cd988252a6d`.
- DS29, `2fc9c0bc420150efe54d0a6a34c8390e3319d748b01c576433fb0578a4e8ce5f`.

The focused evaluator, archive, collector, monitor, and coordinator suite passes
114 tests. Ruff passes for the new tools and their tests. The existing evaluator
and its tests retain pre-existing lint findings. Repository tests, lint, direct
diff review, and independent Sol reviews replace the unavailable Cursor deslop
plugin. No scientific implementation or golden fixture changed.

Plan-only requests for the first scheduled member of each cohort use schema 7,
null inference coordinates, the frozen direct-gap policy, and zero ordinary
recovery targets. Real historical imports for DS26-0002 and DS29-0399 pass fresh
public-store validation without changing their original request paths. The
collector classifies saved DS29-0399 evidence as 56 accepted additions and
DS26-0263 as a fit rejection. These are tool checks on existing evidence, not
new population results. The receipts are under the study's `tool-checks/`.

Read `coordinator/status.json` for the orchestration state and
`staging/ds26/progress.json` or `staging/ds29/progress.json` for attempted coverage.
The coordinator writes completed cohort reports under
`coordinator/reports/ds26` and `coordinator/reports/ds29`. Coverage is not an
accuracy or speed verdict.

After a candidate cohort stops publishing, regenerate its evidence-only report
into a separate output directory. This command runs no inference:

```bash
study_root=/srv/bulk/leo-dev/initial-discovery-20261114/direct-gap-full-001
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B \
  "$study_root/runner/tools/summarize_direct_gap_cohort.py" \
  --manifest "$study_root/plans/ds26-full-direct-gap-historical-001.json" \
  --runner "$study_root/runner/tools/evaluate_initial_discovery.py" \
  --output "$study_root/manual-report-ds26"
```

Substitute `ds29` in the manifest and output names for DS29. The coordinator
owns its existing report directories. Do not rerun numerical execution against
attempted workers or edit the frozen source, manifests, or tools.

Build the Lever produced the coordinator and population collector. Prove It
Works required actual request, historical publication, and saved-outcome checks
before launch. Full population outcomes and a final speed decision remain pending.
