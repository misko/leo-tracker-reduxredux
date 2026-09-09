# RX1 scanner: real feedback queue and scheduler-thread checkpoint

2026-09-09. **Desktop integration passes; ARM execution is blocked on radio
identity verification.** This is a local checkpoint, not a deployed release.
No new RF, firmware, FPGA, kernel or production-service change was made.
Fixed-order scanning and classifier-off defaults are unchanged.

Follow-up: after the user confirmed per-boot SSH key rotation, both full-duration
ARM replays passed with a task-local strict key pin and renewed serial/idle
checks. See the [ARM execution checkpoint](2026_09_09_scanner_threaded_arm_checkpoint.md).
The desktop-only scope and original blocker below describe this checkpoint's
historical state, not the later execution status.

## What this closes

The [previous feedback replay](2026_09_09_scanner_glrt_feedback_replay_checkpoint.md)
verified the SDK's separate wire and observation streams, but did not exercise
the scheduler thread or its handoff queue. Its 5 MS/s saved subset also had no
lightweight-detector positives. This checkpoint addresses both desktop gaps.

The new research-only build connects the real numerical worker, acquisition-owner
SDK observation reader, libiio's bounded single-producer/single-consumer feedback
queue, native adaptive policy and actual scheduler thread. It uses their public
ports and unmodified component sources. The collector also drains the actual
scheduler's visit events and checks their target and source geometry before
registering each visit with the SDK.

The optional `libiio_source` build argument must explicitly identify the foreign
source tree. Original replay builds and modes remain unchanged. The added
`leo-sdk-threaded-shadow-replay-v1` is a research receipt, not a change to a
published recording or wire contract. libiio was read at commit
`42762db3e4a42901c7b9869a3d0d6be7c1147745`; Leo's starting commit was `bebe8ef0`.

Only hardware IO is mocked: dummy profile frequencies, zero-duration recall,
a one-millisecond guard, and a monotonic clock quantized to 121 ms ticks.
The real scheduler must make exactly one actual visit per model tick. A missed
tick fails the replay. **This does not exercise IIO, DMA, interrupts, RF retunes,
the complete OPENM/provider/network path or the final installed package.**

## Saved workload and provenance

The first attempt to reopen the newer comparison's original IQ failed at
`scan-hop-cbd6954a5508690d`: the public read-only store reported that the session
did not exist. That traceback and recipe are retained. No missing bundle was
recreated, and this check does not establish why it is missing.

Instead, the existing hash/geometry-checked loader reopened 96 retained RX1
development dwells: 48 per rate, comprising six original 20 ms slices per dwell.
The input/result inventories, counters, receiver, channel, edge, template and IQ
hashes were checked. The already-opened corpus is not a fresh holdout.

We froze the current `amplitude-diverse-symbol-supported` variant: one blind
confirmation per 120 ms dwell, 512 screening bins, exact-score threshold 0.175,
margin threshold 0.025, and the existing energy/symbol-support checks. No
scientific threshold, golden fixture or tolerance changed.

After evaluating the available development dwells, we ranked complete eight-target
sweeps by passing-dwell count and selected two per rate, with a deterministic
session/sweep tie-break. This is deliberately **post-hoc positive-rich stress
selection**, not a sensitivity estimate or an independent quality result.

| Saved workload | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Available dwells / positive dwells | 48 / 21 | 48 / 12 |
| Selected dwells / positive dwells | 16 / 9 | 16 / 10 |
| Edges with positive examples | Lower and upper | Lower and upper |

The selected 2.5 MS/s sweeps are visits 160–167 and 2080–2087 from
`scan-hop-228b5ad75bb549f3`. The selected 5 MS/s sweeps are visits 2080–2087 from
each of `scan-hop-43cc401e05cbe425` and `scan-hop-db578e8636677ae0`.
Exact original identities and fractional reference candidates are in the
archived manifests.

These 16 dwells per rate repeat in their frozen order. They retain their original
target labels; **an adaptive proposal never causes IQ from a different target to
be substituted or relabeled**. This is shadow execution, not counterfactual RF.

## Verification method

The producer sends 131,072-sample dual-RX blocks, with RX0 and guard samples
explicitly synthetic. Saved RX1 supplies the valid 120 ms portions. Metadata is
delayed by two blocks and every fourth block has 40 ms additional delivery
jitter. Source epochs above `2^53` remain exact integers/decimal strings.

The SDK verifier checks every fractional wire result and independent observation
against the frozen numerical candidates, including source binding, outcome,
ordering and complete terminal inventories. The shadow verifier then applies an
independent Python implementation of the frozen policy to the observation prefix
actually consumed at each decision. Every proposed target, actual target,
active/quiet mask, miss count, cooldown, reason and decision epoch must match.

Offer begin/end intervals account for the producer/consumer race: an observation
can enter the queue before its producer call returns. The verifier rejects
feedback from the future or older than the one-second source-end age limit.
Policy accounting charges the **actual fixed visit**, not the unexecuted proposal.
The scheduler is joined before its policy is released, including failure cleanup.

## Full-duration desktop results

Both rates passed a 4.840 s preflight and a full **300 s elapsed replay**. Each
long run produced **2,479 wire results, 2,479 observations and 2,479 scheduler
choices**, with exact independent policy agreement and unchanged frozen inputs.
No busy, failed, dropped, duplicated or misbound result is accepted by these
successful-run checks.

| Measurement, long desktop replay | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Detected / evaluated miss / healthy unknown | 1,394 / 775 / 310 | 1,550 / 465 / 464 |
| Worker wall p99 / maximum | 5.128 / 5.746 ms | 6.955 / 7.730 ms |
| SDK callback wall p99 / maximum | 0.337 / 2.757 ms | 0.314 / 21.115 ms |
| Scheduler choice wall p99 / maximum | 0.00810 / 2.886 ms | 0.00768 / 0.0213 ms |
| Source-end feedback age at decision, p99 / maximum | 242 / 242 ms | 121 / 121 ms |
| SDK callbacks over nominal block period | 0 | 0 |
| Observations applied before final choice | 2,477 | 2,477 |
| Terminal observations with no later choice | 2 | 2 |
| Proposals differing from actual fixed order | 0 | 0 |

The block periods are 52.429 and 26.214 ms. Both rate processes ran concurrently,
with other desktop checks overlapping part of the run. Timing is descriptive,
not isolated tail qualification or an ARM estimate. Worker, acquisition callback
and scheduler execute asynchronously; their percentile times must not be summed
as one serial hop budget. Callback timing includes the policy offer but excludes
research JSON output and saved-IQ filling. Those activities still influence
arrival timing. Setup includes SDK/policy allocation but not the subsequent
scheduler-thread launch, so startup qualification remains incomplete.

The final two observations at each rate remain completely recorded; the replay
does not invent another hop to consume them. At choice-end snapshots, the
maximum offered-but-not-in-basis prefix was zero. This is **not direct physical
queue occupancy measurement**, nor proof that the queue was always empty.

Reported process-lifetime maximum RSS was 188,476 KiB for the replay parent at
both rates and 21,584/41,668 KiB for the worker children. These receipts are not
isolated steady-state collector memory measurements: the harness holds saved IQ
and research receipts, and launch/history effects have not been separated.
No production ARM memory-headroom claim is made from them.

The one-millisecond guard and quantized clock are modeling assumptions. Neither
the 2,479 visit count nor any ratio derived from it proves live scanner duty.
Repeated detections are not independent signal trials. An evaluated miss is a
scheduling hint; the public positive-only GLRT result remains unavailable, not
an assertion that no signal exists.

## Why the saved replay did not de-prioritize channels

No target became quiet in either long run. At 2.5 MS/s the settled active mask
was 238: CH2L, CH3L, CH4L, CH2U, CH3U and CH4U. CH1L/CH1U alternated unknowns
and misses. At 5 MS/s the settled active mask was 223: every target except CH2U,
which likewise alternated a miss and an unknown. Unknowns break consecutive
miss streaks; positives reset them. Consequently none of these repeated saved
sequences reaches the three-miss demotion condition. Active and still-exploring
targets have equal policy weight, yielding the fixed order.

This is expected policy behavior, **not evidence of an adaptive allocation gain**.
To exercise weighting independently, four explicitly synthetic, real-thread
integration cases use generated pilots on CH1L/CH3L/CH4L and zero IQ on the other
five targets. Both rates and both jitter settings pass 80 visits each. After
startup the masks settle to active 13 / quiet 242, and each case has more than
ten proposals different from the actual fixed visits. The zeros test evaluated
miss mechanics, not real-world false-negative performance. Portable policy/model
tests separately exercise positive-to-miss/unknown-to-positive transitions,
cooldown and recovery. No claim is made that the threaded synthetic workload
itself covers every such transition or injected worker fault.

## Tests, ARM preparation and evidence

**1,009 portable selected tests and five explicitly marked libiio integration
tests pass**, with zero failures, errors or skips. The earlier 550-test focused
run overlaps the 1,009 and must not be added to it. Coverage includes original
and positive replay modes, frames, SDK lifecycle, request validation, pool,
worker, adaptive policy, independent-model tampering and real-thread composition.

The integration module requires `LEO_LIBIIO_SOURCE` explicitly. Run it with
`PYTHONPATH=src:.` and the marked source dependency; it opens no radio. The
portable selection is retained in JUnit, and the integrated cases are in
`tests/scanner/test_glrt_shadow_integration.py`.

ASan/UBSan with leak checking passed both 4.840 s saved workloads, 40 complete
results/observations/choices per rate. The SDK, research adapter and linked
policy/scheduler components are instrumented; the numerical worker and FFTW
are not. This is not a ThreadSanitizer result. Cortex-A9 NEON hard-float
cross-builds pass for the SDK and threaded replay; **neither was run on ARM**.
Ruff, formatting, whitespace and warning-as-error native builds pass.

The [evidence index](evidence/2026_09_09_scanner_threaded_shadow/index.json)
contains recipes, failed preparation/preflight receipts, selected manifests,
raw frame/observation/choice receipts, strict verification summaries, source and
binary hashes, build commands and JUnit logs. IQ, templates, binaries and SSH
host-key files are not committed. Raw work is retained at
`/tmp/leo-integrated-feedback.p7e840`.

## Blocker and remaining gates

USB inventory identifies the intended spare `winbond-db620818a328172c`. However,
strict SSH authentication to its expected physical LAN address `192.168.1.14`
rejected a changed server host key **before the remote serial could be read**.
The network endpoint presents
`SHA256:RnjDewEQlj12QMarth4S9lOTWpydWTb30O/tQpVRf44`. This is an unverified
network claim, not an approved replacement for the pinned key. No upload or
remote benchmark was performed; the key check was not bypassed. The user has
been asked to confirm the fingerprint through a trusted source. Other radios,
production endpoints, excluded serials and the FPGA canary remain untouched.

After identity is resolved:

1. Re-establish serial/ownership and run bounded saved-IQ ARM qualification at
   both rates. Measure startup, per-stage wall/thread CPU, actual queue/backlog,
   feedback age and incremental memory for the exact compatible package.
2. Freeze a genuinely unopened saved-data quality split. Measure false positive
   and false negative behavior, especially active-to-quiet transitions and
   recovery; keep post-hoc stress data out of that estimate.
3. Extend integrated transition/fault workloads where needed. Preserve unknowns,
   cooldown, expiry and fail-open behavior; never invent unsampled adaptive IQ.
4. Only with separate bounded RF authorization, compare fixed detector off/on,
   then fixed/adaptive with detection enabled. Verify source-counter duty,
   actual visits, recording/UI visibility, cleanup and rollback.
5. Complete compatible merge/deployment gates, including dense-analysis capacity.
   This desktop checkpoint does not authorize or claim a production release.
