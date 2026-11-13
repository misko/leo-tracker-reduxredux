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

## Direct timing-gap follow-up

The reviewed eight-pair follow-up launched on 2026-11-13 at 19:44:34 UTC as
`leo-direct-gap-followup-001.service`. Its frozen scope is
`/srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/scope-receipt-v2.json`
(SHA256 `9fb261f6da6b7ff0ab4531b2ab09afcee4358ab1f4461c824a0bdbc443e324f5`).
The receipt binds the preselected fresh groups, consumed-group exclusions,
source, evaluator, native build, 16 plan-only requests and the eight-pair
schedule. The two initial fresh manifests were superseded before any numerical
launch because they did not reproduce the consumed-group selections. Only the
following corrected manifests were launched, in this order:

| Manifest under `direct-gap-followup-001/plans/` | Whole recording | New pairs and role order | Manifest SHA256 |
| --- | --- | --- | --- |
| `ds26-fresh-v2.json` | DS26-0263 | One, baseline then candidate | `37575847c275e5673d9b2290c8dccf8dd98c7e9b57adb2fdaf51b9202d6167e1` |
| `ds29-fresh-v2.json` | DS29-0126 | One, baseline then candidate | `8f8deb24a41c074ea6a66308c4b6dfe39fb3d9f7a80c3ce347678011bb778aca` |
| `ds29-repeat.json` | DS29-0399 | Three, baseline/candidate, candidate/baseline, baseline/candidate | `8b0579f42093505b11e7adfd6bee50b5e124a3bf46ed86d4fa9484a601f1af66` |
| `ds26-repeat.json` | DS26-0002 | Three, baseline/candidate, candidate/baseline, baseline/candidate | `c89426e1f2993166d4fe4e8aa6b1423c8f454e3e131aa80ec2d1296f0b93ef4b` |

Both roles use the same frozen fast-v5 source, evaluator and native manifest
under `/srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-worker-001`.
The candidate alone requests `direct-timing-gap-v1`; both roles retain zero
ordinary recovery targets and legacy initial discovery. The frozen coordinator
is `direct-gap-runner-002/tools/evaluate_initial_discovery.py` (SHA256
`0962e4fb4dc37017a4f2bab28c5b497fad9127291e024e1976ee0420c5437e60`).
Every complete worker uses CPU 21, one BLAS/OMP/MKL thread and a 2,400-second
cap. The exact launched service command was:

```bash
systemd-run --user --unit=leo-direct-gap-followup-001 --collect --same-dir \
  --property=CPUAccounting=yes \
  --setenv=OPENBLAS_NUM_THREADS=1 --setenv=OMP_NUM_THREADS=1 \
  --setenv=MKL_NUM_THREADS=1 --setenv=PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/taskset -c 21 /bin/bash -lc '
set -e
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-runner-002/tools/evaluate_initial_discovery.py run --manifest /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/plans/ds26-fresh-v2.json --cpus 21
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-runner-002/tools/evaluate_initial_discovery.py run --manifest /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/plans/ds29-fresh-v2.json --cpus 21
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-runner-002/tools/evaluate_initial_discovery.py run --manifest /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/plans/ds29-repeat.json --cpus 21
/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-runner-002/tools/evaluate_initial_discovery.py run --manifest /srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/plans/ds26-repeat.json --cpus 21
'
```

The actual invocation ID, initial PIDs, full shell script and scope binding
are saved in `direct-gap-followup-001/launch-receipt.json` (SHA256
`cdfa75acbd3ccc3b61d4e4ba75b77d6f3a18b02254326de0a0ef420ad93eb064`).
Monitor with `systemctl --user status leo-direct-gap-followup-001.service`
and `journalctl --user -u leo-direct-gap-followup-001.service -f`. This
command records the launched run; do not execute it again against attempted
workers. If a manifest exits nonzero, `set -e` stops the sequence. Keep its
failed or timed-out report and execution receipt, determine exactly which roles
were attempted, and start only untouched later manifests in a new durable unit
using the same frozen bindings. Never silently retry an attempted numerical
worker. The original-v3 campaign remains a separate timing denominator;
these contended pairs report complete-worker CPU/wall and c=0/fitted-c
position and frequency outcomes separately.
