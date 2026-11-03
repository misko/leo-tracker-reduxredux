# Modular ARM goal: completion evidence

This is an evidence map, not a declaration of completion. The optimized
queue-16 experiment failed with seven dropped dwells; the queue-32 trial now
passes all scientific, lossless, latency, capacity and loaded-throughput checks
(`cadence-four-queue32-v1/acceptance-evaluation.json`). The latest requested
extension—three distinct recordings with per-stage server comparisons—is
complete. Queue 48 loses no dwells, but latency reaches 5.479 seconds and the
two loaded downstream intervals take 304.410 and 310.180 seconds. Full native
raw-IQ controls expose a separate fit-summary-sensitive identity/partition bug
that changes positioning results despite identical memberships. The goal remains
incomplete. See the [completed mixed-recording report](../2026_10_01_arm_three_scan_sequence/README.md).
Historical remaining-work cells below refer to the preceding audit; completed
four-scan and mixed-recording receipts supersede those cells. Their failed
runtime and full-chain reproducibility gates remain open.

| Requirement | Current evidence | Qualification limit / remaining work |
|---|---|---|
| Component-owned unit and contract tests | `cadence-four-threshold-pgo-v1/bench-tests.log`: 104 tests; `replay-contract-tests.log`: 66 tests. Prepared-threshold host research build runs its component tests; physical bound, interval, location, session and immutable-orbit tests pass. Fresh PGO additionally passes location, stencil, session and immutable-orbit tests. | Header-level ASan/UBSan test passes; its linked library is uninstrumented, so this is not whole-pipeline sanitizer coverage. |
| Reproduce 16,191 observations and all five frozen trackers | `cadence-three-observer-v2/evaluation.json` verifies three complete scans. `cadence-four-threshold-pgo-v1/frozen-trackers-current-audit.json` rechecks all 18 frozen output artifacts across five methods and three repeats. `modular-track-port-v1/receipt.json` qualifies all five supplied-track adapters on host and ARM. | Complete the new four-scan output comparisons. Frozen tracker reproduction does not mean all five algorithms are used in one deployed chain. |
| End-to-end recorded IQ with independent comparisons | The prior three-scan run compares every detector/checkpoint and complete downstream output. `release/*.evaluation.json` retains server membership comparisons; `published-location-comparison.json` compares native/server association scoring on published tracks. `prepared-threshold-full-v1/` verifies all 400 ARM points, direct host tolerance and final association bytes. | New loaded-run comparisons pending. Native tracking differs from server segmentation; the 400-point search exhausts its budget and is not global convergence. |
| PLUTO+ deployment and complete resource measurements | Pinned executables execute at 192.168.1.15 with local recorded IQ. The native cadence controller records fixed origins, process lifetimes, queue inventory and sampled aggregate RSS; each stage records CPU/wall/RSS, and detector events support arrival-to-finish latency. | Complete collection and plotting of the new run. Five-second aggregate RSS sampling may miss peaks and count shared pages more than once; per-process high-water marks remain available. |
| Sustained original cadence, bounded queues, no silent loss | Previous three-scan run is lossless but **fails loaded throughput**, explicitly recorded in `cadence-three-observer-v2/loaded-cadence-evaluation.json`. Four-scan acceptance criteria were written before execution; `evaluate_loaded_cadence.py` enforces three loaded intervals below 300 seconds and finishing before the next scan is ready, with science/lossless checks required. | **Open.** Await and evaluate the active four-scan test. Its final unloaded drain cannot prove loaded throughput. |
| Reproducible report, commands and limitations | Build scripts, source snapshots, profiles, executable/input hashes, per-stage outputs, timing receipts and evaluator commands are retained under the qualification report. `docs/native-pipeline-replay.md` describes public meanings and private adapters. | Final timing/recovery table and cadence plots remain pending the current run. Pi/RTL-SDR, live RF acquisition and genuinely longer recordings remain separate hardware/data qualifications. |

## Scientific interpretation

The frozen coarse-seeded tracker represents 55 of 62 eligible server segments,
with 45 one-to-one matches, excluding only the previously agreed reference #10.
Duration buckets are 7/9 short, 23/25 medium and 25/28 long. Of 80 output tracks,
35 lack a one-to-one reference match and 26 have no reference support. Those
counts are agreement proxies, not physical identity or false-positive labels.

The original frozen tracker export and fresh native projection are distinct
checkpoints: their coarse tracker results contain 5,254 and 5,255 distinct used
candidates respectively. Each is compared against its own pinned control; the
two figures must not be silently interchanged. Fresh native seed/track outputs
match their host counterparts exactly (`fresh-graph-tracking-v1/receipt.json`).

Published-track association comparisons retain all 59 satellite and time-offset
choices at each of two sites; residual differences from orbit interpolation are
reported explicitly. That comparison does not establish identical positioning
when the native and server trackers supply different memberships.

Repeated recordings establish a bounded load horizon, not new independent RF
data or longer scientific history. No new RF acquisition is authorized by this
qualification; IQ remains local to PLUTO during processing.
