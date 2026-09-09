# RX1 scanner: independent feedback-stream qualification

2026-09-09. Local offline checkpoint; **not deployed or remotely merged**.
This extends the existing SDK replay, not the runtime detector or radio image.
No radio, network capture, FPGA, firmware, kernel or production service was
accessed or changed. Fixed scanning and classifier-off defaults are unchanged.

## Gap addressed

The previous modeled producer replay verified the original unqualified GLRT
wire stream. It did not consume the positive-only SDK's separate observations
that drive adaptive scheduling. Successful recording metadata alone could not
demonstrate that this feedback stream was complete, correctly bound or timely.

The new explicit `positive-feedback-v1` **research replay** option opens the
existing positive-only SDK with exact score >=0.175 and margin >=0.025. It
copies at most eight observations per poll from the same acquisition owner,
alternating before/after wire-frame consumption. A separate terminal receipt
checks that both consumers receive every source result exactly once. The old
invocation, unqualified behavior and replay schema remain available unchanged;
the new mode has a separate research schema. No public persisted contract changes.

The verifier independently derives the expected choice from frozen numerical
candidates. A passing candidate takes priority over a larger-margin candidate
that fails the exact-score threshold. Source session/generation, visit, exact
uint64 interval, rate, receiver, target, outcome, fractional measurement and
both terminal inventories must match. Changed thresholds, duplicate/missing/
reordered observations, invalid timestamps and impossible consumer order fail.
Source counters above `2^53` remain exact strings/integers.

The distinction needed by cooldown remains intact:

| Detector outcome | Scheduler observation | Public GLRT verdict |
| --- | --- | --- |
| A complete fractional candidate passes | Detected | Starlink candidate evidence |
| Completed bounded search; no candidate passes | Evaluated miss | Unavailable, not absence |
| Fractional estimate incomplete; no passing candidate | Unknown | Unavailable |
| Worker/input failure | Unhealthy unknown | Unavailable |

The successful replay rejects failed/busy/incomplete-input results; existing
SDK and policy component tests separately cover cancellation/failure, unknown
versus miss, cooldown, expiry and latched fallback. This is not a claim that
the successful replay injected all those faults into a streaming radio.

## Workload and limits

Use the existing first 16 saved RX1 dwells per rate from the
[symbol-support checkpoint](2026_09_08_arm_presence_symbol_support_checkpoint.md).
Published manifest hashes, packs, templates and numerical implementation source
hashes are checked before use. These 32 already-opened development dwells are
repeated in frozen order, not newly collected or an independent quality holdout.

The current SDK and symbol-supported native worker are rebuilt locally. The
worker uses the same frozen scientific flags and FFTW backend as the reference.
Research identities bind the actual worker hash and explicit threshold/profile
configuration; they are **not production release identities**.

Each modeled cycle has 120 ms valid saved IQ plus a **synthetic 1 ms guard**.
Blocks contain 131,072 dual-RX samples; RX0 and guard samples are sentinels.
Visit metadata arrives two blocks late, and every fourth block receives 40 ms
additional delivery jitter. The original source identities remain preserved,
but arrival times and replay counters are modeled. No retune, original DMA
timeline, IIO/IRQ/network load or unsampled adaptive IQ is fabricated as RF.

The two sample-rate processes run concurrently on this desktop. Other local
regressions/sanitizer checks overlap part of the run. Timing is descriptive,
not an isolated tail benchmark, an ARM speed estimate or a live-duty measure.
SDK callback cost excludes research JSON output and saved-IQ filling; those
costs still influence modeled arrival lateness. Startup precedes the replay
clock. Observation latency includes waiting for the next acquisition callback.

## Results

Both 300-second executions pass, each with **2,479/2,479 wire results and
2,479/2,479 independent observations**. Every fractional result matches the
frozen reference, both streams terminate completely, and source/build/input
identities remain unchanged. No busy, dropped, duplicated, failed or misbound
result is accepted by this verification.

| Desktop measurement | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| SDK callback wall p99 / maximum | 0.420 / 4.004 ms | 0.363 / 5.216 ms |
| Observation polling/copy wall p99 | 0.00288 ms | 0.00277 ms |
| Worker wall p99 / maximum | 5.892 / 29.502 ms | 7.600 / 62.608 ms |
| Input-ready callback to feedback p99 / maximum | 92.738 / 203.068 ms | 66.484 / 104.937 ms |
| Callbacks exceeding nominal block period | 0 | 0 |
| Detected / evaluated miss / healthy unknown | 930 / 1,394 / 155 | 0 / 1,704 / 775 |

The nominal block periods are 52.429/26.214 ms, respectively. A fast observation
copy does not mean instant feedback: most delivery latency here is waiting for
another modeled callback. These are actual elapsed desktop replays, not
accelerated counter spans; they are still **not live 300-second captures**.

The preselected 5 MS/s subset contains **no passing lightweight-detector
results**; its long run therefore verifies miss/unknown feedback, not sustained
positive-feedback workload at that rate. The short generated-pilot regressions
exercise positive results at both rates. The 930 detections at 2.5 MS/s repeat
six saved source dwells; they are not 930 independent signal trials. Differences
between these source subsets must not be presented as sample-rate sensitivity.
Representative positive-heavy/mixed 5 MS/s workload remains a qualification
gap alongside real ARM acquisition contention.

## Tests and setup findings

**961 selected tests pass**, zero failures/errors/skips. They cover both sample
rates, four delay/jitter combinations, original/positive modes, real worker
numerical parity, frame contracts, SDK lifecycle, pool/worker behavior and the
adaptive policy. The earlier focused run passed 502 overlapping tests; these
counts must not be added together. No golden fixture or tolerance changed.

The SDK and updated consumer also cross-compile for Cortex-A9 ARM hard-float.
Those binaries have **not** been executed on a radio; a build is not a timing
or deployment pass.

ASan/UBSan/leak-checked SDK and replay-consumer executions pass both rates:
16 saved dwells each, **32 wire results and 32 feedback observations**. The
unchanged numerical worker and external FFTW library are not instrumented by
these runs. Short uninstrumented saved-IQ preflights also verify 8+8 results
and observations before starting the long tests.

Two setup errors were retained rather than hidden: the first recipe looked up
an archived manifest without its `.gz` index suffix; the next was correctly
rejected because historical template files were group-writable. New local
hash-identical copies use mode 0600. Original files and SDK trust checks are
unchanged. The first sanitizer attempt hit the same template-permission check;
the corrected run uses the private copies. No receiver was involved.

Ruff, formatting, whitespace and warning-as-error native builds pass. The
[evidence index](evidence/2026_09_09_scanner_glrt_feedback_replay/index.json)
retains recipes, test logs, build identities, raw feedback/frame receipts,
verification summaries and failed setup attempts. IQ and executables are not
committed. Raw owned work remains in `/tmp/leo-sdk-feedback.MD8dVh`.

## Next release gates

This closes a desktop feedback-stream verification gap, not the complete
adaptive-scanner goal. Next: exercise the exact packaged SDK, bounded handoff
queue and scheduler under integrated ARM load, with startup, memory, feedback
age and backlog measurements. Keep shadow analysis tied to actual sampled
targets. Independent detector/policy quality, dense-analysis capacity, explicit
bounded RF authorization, compatible merge/deployment and real recording/UI/
rollback checks remain required. No ARM or live-duty pass is inferred here.
