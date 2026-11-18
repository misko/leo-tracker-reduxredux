# Bounded accuracy-repair experiments

The objective is to recover useful observations while retaining most of the
fast-v5 wall-time improvement. Two research policies use optional execution
ports. Published requests, persisted v5 contracts and default behavior are
unchanged.

`selective-gap` applies a conservative prediction screen before the existing
independent timing-gap annotation, inclusion and exact audit. Predictions use
the incumbent's calibrated phase and covariance; either calibration arm can
retain the common candidate. The distance threshold was fixed before examining
the development probe outcomes. Position uncertainty is not integrated, so this
threshold has no calibrated false-negative guarantee.

`omitted-tracks` scores wholly unowned native tracks outside the initial curved
population, then sends at most two tracks through the existing independent
recovery pipeline. Proposed satellite labels and aliases are diagnostic only;
annotation regenerates them. Two tracks can still trigger multiple fits,
numerical retries and joint recovery. All that work belongs in the timing.

`omitted-track-one` is an explicit refinement with one proposal. It reproduces
the two-proposal scientific results exactly on the two beneficial development
cases while halving annotation phase fits from 60 to 30. The policy is opt-in;
the default experimental variants remain unchanged.

## Fixed probe evidence

The gap screen retained the exact accepted components in DS26-0012, DS29-0399,
DS26-0066 and DS26-0098. It also retained harmful DS29-0163 and the component
associated with the known DS26-0104 ownership failure. It rejected the previously
unsuccessful DS26-0130 component, but retained the expensive rejected DS26-0050
component. Eight saved paired objectives replayed exactly. Individual screening
operations took 0.229–1.128 seconds; these are not complete-worker measurements.

The omitted-track selector ranked useful tracks first in DS26-0050 and
DS29-0082, missed the useful DS26-0130 track, and ranked a known harmful track
first in DS29-0289. Its four saved paired objective replays agreed within 2e-9.
Individual nomination calls took 0.247–0.384 seconds. Neither policy establishes
that a confident satellite identity improves localization.

## Evaluation scope

Diagnostic worker pairs are DS26-0012/DS29-0399 for selective-gap and
DS26-0050/DS29-0082/DS29-0289 for omitted-tracks. A seeded random selection fixed
DS26-0311 and DS29-0123 before any complete-worker outcomes. Both policies and a
fresh baseline run on those two recordings. Known development recordings and
their whole recording groups are excluded from the untouched selection.

All roles use identical frozen code and native bindings, one BLAS thread,
both calibration arms, native preparation, downstream inference, all eight PNGs,
and experimental archive serialization. Evaluation coordinates reach only the
coordinator after inference. Role order is seeded random, not guaranteed
alternation. The host is contended; single-run wall and CPU differences are
descriptive, not a general speed qualification. This producer does not perform
the production publication step, so historical production clocks are a different
timing scope.

The full plan includes all 159 DS26 and 615 DS29 members, including missing
inputs: 774 recordings and 2,322 workers for baseline and both candidates. It
does not run automatically. A full plan is not evidence of full evaluation.

The initial bulk filesystem stall was avoided with explicitly bounded local
staging under `/home/mouse9911/.cache/accuracy-repair-20261115`, retaining a
20 GiB free-space floor and a 5 GiB staging limit. Full evaluation should use
healthy bulk storage, rather than exceeding that local limit.

## Reproduction

Use the repository virtualenv. Freeze `src` and these four tools together:
`evaluate_accuracy_repair.py`, `evaluate_algo07.py`,
`evaluate_initial_discovery.py`, and `initial_discovery_archive.py`.
Build the native artifact against that frozen source using
`leo.analysis.localization_v4.backend.build_native`; manifests bind absolute
source and wrapper paths as well as content hashes.

The current frozen source is
`/home/mouse9911/.cache/accuracy-repair-20261115/frozen-001/src` with digest
`sha256:36be340683b030af69ed99194d3c8fbe976093d49d16c4cfb7be4960344898ae`.
Its native manifest is
`/home/mouse9911/.cache/accuracy-repair-20261115/native-001/manifest.json`.
The original frozen evaluator is under `frozen-001/tools`. The final evaluator
under `frozen-002/tools` adds the one-proposal role and scientific-validation
caching without changing the frozen scientific source or native artifact.
Cache hits still freshly hash archive bytes; cached validation binds the
validator, input request, worker projection, policy, source and native hashes.

Plan a few cases with `plan --profile diagnostic --cases DS26-0012,DS29-0399
--variants selective-gap`, or a random whole-recording selection with
`plan --profile holdout --groups-per-dataset 1`. Plan all frozen members with
`plan --profile full`. Each command also requires `--manifest`, `--output`,
`--source-root` and `--native-manifest`; `plan --help` describes these arguments.
Use fresh output directories for new experiments.

Execute a bounded portion of a saved plan:

```bash
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  /home/mouse9911/.cache/accuracy-repair-20261115/frozen-001/tools/evaluate_accuracy_repair.py \
  run --manifest /home/mouse9911/.cache/accuracy-repair-20261115/holdout-plan.json \
  --cpus 18 --max-recordings 2 --max-wall-seconds 1800
```

Repeat the same command to resume completed workers without rerunning them.
Each worker must have its complete declared deadline remaining before admission;
the invocation stops rather than shortening the scientific budget. Interrupted
started workers are retained for investigation. `report --manifest PATH`
revalidates completed archives and regenerates accuracy, fit, ownership, coverage
and wall/CPU comparisons without inference.

## DS26 four-configuration repeated campaign

The explicitly authorized DS26 campaign started at 2026-11-15 18:32:18 UTC.
Its frozen runner, manifests, logs and results are beneath
`/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001`.
It retains all 159 inventory members and runs baseline, selective-gap,
omitted-track-one and omitted-tracks twice: 1,272 expected outcomes.
DS26-0172 has no native run and contributes eight explicit missing outcomes;
1,264 workers have available inputs. Completion and failure counts must be
read from the result files; launching the campaign does not establish coverage.

The first role order is seeded random for each case, and the second is its
exact reverse. Recording groups and both repetitions stay on one fixed lane.
Four lanes use physical CPUs 16, 17, 18 and 19, with one worker per lane and
one BLAS thread. Existing historical work uses CPU 21. Other host activity is
not isolated, so runtime differences remain descriptive. The coordinator records
load and CPU pressure before and after workers. It admits complete 1,200-second
worker deadlines in bounded 1,800-second waves, automatically resumes finished
outcomes, and preserves interrupted started workers for investigation.

The user service `leo-ds26-four-configs-twice-20261115.service` owns execution;
`systemctl --user status leo-ds26-four-configs-twice-20261115` inspects it.
`run_accuracy_repair_campaign.py plan` freezes CPU assignments and coordinator
bindings before inference; `run --campaign PATH` executes the complete saved
campaign, and `report --campaign PATH` regenerates reports without inference.

Results include `comparison.json`, `repeat-comparison.json`, `report.md`,
`repeat-report.md` and `campaign-progress.json`. The repeated comparison retains
all 159 cases in coverage, reports all successful workers and the same cases
successful across all four configurations and both repeats, and gives mean,
median, p90, p95, p99 and maximum position errors, wall times and CPU times.
Frequency scores and residuals remain separate from localization accuracy.
Both calibration arms are reported. Per-case repeat deltas, ratios and
population coefficients of variation accompany aggregate variation summaries.

The original transient service disappeared during a simultaneous disruption of
multiple unrelated user services at 2026-11-17 17:57:51 UTC. It did not complete
the campaign. Three started workers had no completed result or archive:
DS26-0126-r0/omitted-tracks, DS26-0217-r0/omitted-track-one and
DS26-0309-r0/selective-gap. Recovery preserved their original records and partial
artifact hashes under `recovery-20261118-001/evidence`, then recorded explicit
externally interrupted failures with incomplete CPU accounting. These attempts
are excluded from accuracy and timing comparisons and were not rerun.

At 2026-11-18 03:10:39 UTC the same service name resumed through an enabled
persistent user unit with restart on failure. It uses
`recover_accuracy_repair_campaign.py` as a preflight around the unchanged frozen
coordinator. The preflight refuses live workers, possible completed evidence,
request drift or conflicting execution locks; it preserves every finished
outcome. Recovery accounted for 1,024 outcomes and left 248 unstarted outcomes.
Scientific source, manifests, native bindings, CPU lanes and timeout policy
remain frozen. The shutdown journal is saved beside the recovery evidence.

## Validation

The 69 new component and harness tests pass. A separate 138-test application
and direct-gap regression suite also passes; these counts overlap. Review checked
reference isolation, whole-recording split labels, score preservation, canonical
target selection, unchanged default paths, and full-work accounting. All nine
fresh baselines match the original fast-v5 endpoints, scores, residuals and
complete owner maps exactly. Independent review verified all 20 scientific
archives, their hashes, all eight PNGs and the absence of evaluation references.

All workers completed, with no final scientific fit failures or exhausted fit
budgets. Across recovery runs, 330 annotation phase fits used 8,944 evaluations;
16 primary optimizer failures completed fallback successfully.

## Completed bounded results

These are 11 comparisons from 20 workers on seven recordings, including two
preselected random whole-recording holdouts. The full 774-member sweep has not
run. Each timing compares a candidate with its own fresh fast-v5 baseline.
Positive time changes are overhead, not speedup. Errors are distances in metres;
DS29 uses operator reference coordinates rather than surveyed ground truth.

| Recording | Policy | Error c=0 | Error fitted-c | Wall change | CPU change |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0012 | selective-gap | 1096.9 → 609.1 | 1034.2 → 583.4 | +3.9% | +3.4% |
| DS29-0399 | selective-gap | 1269.4 → 377.5 | 1311.3 → 466.1 | +16.8% | +15.2% |
| DS26-0050 | omitted-tracks, two | 2144.3 → 1607.8 | 2098.4 → 1710.4 | +70.4% | +72.2% |
| DS29-0082 | omitted-tracks, two | 566.9 → 115.4 | 517.2 → 486.2 | +56.1% | +58.1% |
| DS29-0289 | omitted-tracks, two | 948.7 → 954.0 | 1143.3 → 1148.7 | +94.8% | +92.2% |
| DS26-0050 | omitted-track-one | 2144.3 → 1607.8 | 2098.4 → 1710.4 | +20.2% | +41.9% |
| DS29-0082 | omitted-track-one | 566.9 → 115.4 | 517.2 → 486.2 | +8.8% | +28.9% |

Both policies preserve all final scientific outputs on DS26-0311 and DS29-0123.
DS26-0311 spends 6.1% extra CPU rejecting an ambiguous omitted-track proposal.
DS29-0123 has no eligible omitted proposal; its apparent 11.5% wall improvement
comes with only 0.8% CPU reduction and is timing noise, not demonstrated
algorithmic acceleration. Two holdouts cannot establish population or tail
accuracy. The one-proposal refinement was evaluated on the two beneficial
development cases, not on these holdouts or DS29-0289.

Selective gap restores 95 and 56 observations, the original ownership maps,
and essentially the original v3 positions. The screen costs 0.51 and 0.27 seconds;
full gap work costs 38.35 and 48.74 seconds. Restored observations also change
downstream search, so stage cost and net wall overhead need not match.

The second omitted proposal contributes no final owners in all three diagnostic
cases. Removing it preserves the two beneficial results and avoids unused fits.
Its 9–20% observed wall overhead nevertheless accompanies 29–42% CPU overhead.
The one- and two-proposal runs had different fresh controls and contention;
their absolute wall times must not be compared as a controlled speed ratio.

### Frequency fit versus localization

Both c=0 and fitted-c use the same observations, candidate selections and
budgets within each policy. Localization improvement is measured independently
against the references. Frequency scores change when observations are added,
so raw score changes do not isolate improvement on a fixed population.

For DS29-0082, the fitted-c selected-fit RMS on the original matched observations
changes from 96.68 to 96.80 Hz, while position error improves from 517.2 to
486.2 m. On those same original observations c=0 RMS changes from 97.00 to
97.15 Hz, while position error improves from 566.9 to 115.4 m. Lower fitted-c
residuals therefore do not imply a better position. On DS29-0289 both frequency
scores increase by approximately 480 after adding 42 observations, yet position
errors worsen by approximately 5 m. All arm-specific score and matched-residual
comparisons are retained in the machine-readable report.

### Decision and next evaluation

Keep both policies opt-in. Selective gap is the stronger accuracy/cost candidate,
but its saved probes still retain a known harmful case and a known failing case.
Keep only one omitted proposal in the next evaluation; independent inclusion
and numerical replay remain its major costs. Do not promote the two-proposal
policy or claim a new full-dataset speedup from these measurements.

The next bounded gate should include DS29-0163 and DS26-0104 for selective gap,
DS29-0289 for the one-proposal policy, and additional randomly selected recording
groups. Repeated fresh pairs under lower contention are needed for a defensible
wall-time estimate. A subsequent full plan can select the refined roles with
`plan --profile full --variants selective-gap,omitted-track-one` using the
`frozen-002/tools/evaluate_accuracy_repair.py` evaluator. This creates a plan;
execution remains explicit and resumable in bounded invocations.

Full numeric results and input hashes:
`/srv/bulk/leo-dev/accuracy-repair-20261115/final-report/summary.json`.
Readable comparison:
`/srv/bulk/leo-dev/accuracy-repair-20261115/final-report/report.md`.
