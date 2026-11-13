# Running the frozen initial discovery evaluation

The maintained entry point is
[`tools/evaluate_initial_discovery.py`](../../tools/evaluate_initial_discovery.py).
It plans without inference, binds each role's actual source/evaluator/native
artifacts, checks the complete requested numerical job, and validates metrics
through the public store. The archive helper verifies copies outside worker
timing and preserves absolute publication paths. The 44 owned runner/archive
tests cover randomized recording groups, missing/failed jobs, tampered requests,
public-evidence binding, resource admission and archive corruption/crash recovery.

The reviewed seed-only policy was selected using DS26 development evidence
before reading DS29 qualification outcomes. Request schema6 names
`anchor-round-robin-v1` seeds and `legacy` ranking; the direct baseline is
unchanged fast v5 with zero RF recovery targets. See the decision and limits in
[`initial-discovery-plan.md`](initial-discovery-plan.md).

Frozen runner003, manifests and current outputs are in
`/home/mouse9911/.cache/initial-discovery-20261113`. Its
[`README.md`](/home/mouse9911/.cache/initial-discovery-20261113/README.md) contains
the execution records and earlier development commands. The persistent user
service `leo-initial-discovery-screen-sequence-003.service` finishes the active
seed development child, runs DS29 qualification, then DS26 qualification, then
the separate ranking development screen. It uses CPUs12,13,14 throughout and
shares the existing numerical lock. Its coordinator log is
`/home/mouse9911/.cache/initial-discovery-20261113/screen-sequence-003.log`.

The exact frozen qualification command for DS29 is:

```bash
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B \
  /home/mouse9911/.cache/initial-discovery-20261113/full-runner-003/run_discovery_pairs.py run \
  --manifest /home/mouse9911/.cache/initial-discovery-20261113/plans/ds29-quick-seed-only-003.json \
  --cpus 12,13,14
```

Use `ds26-quick-seed-only-003.json` for DS26. The frozen four recording groups
are DS29-0336/0062/0396/0412 and DS26-0156/0108/0255/0317. Their assignments use
seed `initial-discovery-ds26-ds29-20261113-v1`; all 16 previously consumed DS26
groups are excluded. Qualification outcomes must not tune a policy while those
same groups are still called independent.

Each output directory contains `comparison.json`, `progress.json` and eventually
`terminal.json`; per-role `*-work.json` binds freshly validated public evidence.
Missing, failed, timed-out, evaluator-failed and absent rows remain visible.
Only complete matched pairs enter scientific metrics. Report c0 and fitted-c
position errors separately from frequency scores and ownership changes. DS29's
explicit reference map contains operator locations rather than surveyed GNSS
truth. Busy-host wall and CPU observations do not establish a repeatable speed
gain; that requires fresh alternating serial repetitions.

The candidate-only full phase uses the separately reviewed runner004 with
`--historical-baseline-root`: original fast-v5 reports keep their actual source,
request paths, run identities and publication locations. Import receipts bind
the unchanged report and execution command. Every complete import is checked
through the public store. Historical and candidate rows are copied for
comparison with timing disabled before any paired arithmetic; the accuracy
report contains no timing ratios. Fresh quick/repeat evidence remains separate.

Full manifests retain all 159 DS26 and 615 DS29 members, including four missing
inputs. An unfinished original control stays pending; candidate coverage and
paired coverage are reported independently. Scientific failures and missing
inputs remain visible. Candidate execution can finish while the original
campaign is still producing controls. The inference-free refresh command
imports newly available controls and completes the accuracy comparison:

```bash
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B \
  /home/mouse9911/.cache/initial-discovery-20261113/full-runner-004/run_discovery_pairs.py refresh \
  --manifest /home/mouse9911/.cache/initial-discovery-20261113/plans/ds29-full-seed-only-historical-004.json
```

The corresponding candidate-only full execution command is:

```bash
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B \
  /home/mouse9911/.cache/initial-discovery-20261113/full-runner-004/run_discovery_pairs.py run \
  --manifest /home/mouse9911/.cache/initial-discovery-20261113/plans/ds29-full-seed-only-historical-004.json \
  --cpus 12,13,14
```

The durable continuation service is
`leo-initial-discovery-full-sequence-004.service`. It waits for the entire 003
sequence to finish, validates both four-recording quick cohorts and their
public receipts, then acquires the same numerical lock and runs candidate-only
DS26 followed by DS29. Any quick runtime/contract failure stops admission and
preserves the evidence. Its state and log live under the NVMe experiment root;
the service is activated only after runner004 review and source freezing.
No additional RF collection is authorized by this runner.
