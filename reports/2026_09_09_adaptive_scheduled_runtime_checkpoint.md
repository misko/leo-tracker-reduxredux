# Adaptive scanner: scheduled runtime and source-bound publication

2026-09-09. The scheduled application now captures explicit shadow/adaptive
sessions through the concrete Pluto adapter, publishes immutable dual-RX IQ
after cleanup, and independently publishes source-bound GLRT evidence.
**This remains default-off development work, not a production deployment or
detector/ARM/RF qualification. Adaptive history/UI and actual-time analysis
integration are still pending.**

No radio connection, RF collection, production-service change, firmware flash,
FPGA or kernel change was performed. Network fixtures connect exclusively to
127.0.0.1. Their nominal 192.168.1.* identities and physical controls are
substituted fixtures, never contacted radios.

## Implementation

1. `PlutoAdaptiveHopRadio` owns a distinct adaptive session, never a permissive
   fixed-hop adapter. It admits an exact physical-LAN identity, excludes the
   prohibited serial, requires the positive-only GLRT profile, and binds detector
   generation to the pinned policy generation. Unsupported metadata clients
   fail admission without silently disabling adaptive behavior.
2. One non-daemon producer owns upstream iteration, cancellation and close.
   Read-ahead is bounded. Normal completion and cancellation drain the upstream
   final completed visits exactly once; all delivered visits must match the
   validated terminal receipt. During recovery, draining an abandoned queue
   cannot be mistaken for IQ delivered to storage. A timed-out live producer
   retains logical ownership and cannot be closed concurrently or reopened.
3. Runtime opt-in uses `LEO_SCANNER_HOP_POLICY=fixed|shadow|adaptive`; `fixed`
   remains the default. Shadow/adaptive require an enabled persistent-hop
   scanner and `LEO_SCANNER_GLRT_MODE=positive-only-v1`, with the existing exact
   algorithm/configuration hashes. The rate schedule, 300 s duration, 120 ms
   valid dwell, 1,200 s cadence, IF/bandwidth, guards, gain and both recorded RX
   remain unchanged. Only RX1 is classified. No detector threshold changed.
4. Scheduled capture retains storage admission, exclusive radio authority,
   exact alternate-iiOD startup/cleanup and the pre-publication safety barrier.
   A pre-cancelled run performs no radio setup. IQ publishes only after radio
   close and verified alternate-daemon cleanup; classifier publication happens
   after authority release. Classifier failures remain explicit warnings and
   cannot undo valid IQ or trigger recapture.
5. New read-only reservation queries distinguish missing from unpublished
   recordings. The scheduled operation keeps its stable ID. Fixed/adaptive
   namespaces cannot acquire the same slot again after a mode change, including
   retained failed staging. Checks repeat inside acquisition authority.
   Existing shadow sessions cannot be relabelled adaptive. Same-mode retries
   verify/reuse the original IQ, policy generation and classifier evidence,
   without reopening the radio or consulting a previous radio object's results.
6. A separate adaptive GLRT binding validates actual event targets, source
   intervals, RX, rate, policy generation, manifest hash and terminal inventory.
   The detector inventory covers **all started events**, while retained IQ
   covers complete visits. A cancelled last event therefore remains an explicit
   unavailable result, not missing delivery. A nominal 120 ms interval alone
   never proves IQ existed: actual searched samples must lie within delivered
   source IQ and before capture stopped. No positive-only result may assert
   signal absence. Fractional offsets remain separate from integer epochs.
7. The durable supervisor recognizes a separate adaptive result type. A slot
   succeeds only for completed, source-attested capture meeting its duty target;
   cancelled, low-duty and unattested captures do not become successful merely
   because a file was published. Detector qualification is not implied by
   recording health. Without a source origin, duty displays as unavailable in
   the operation outcome, not a measured zero. Fixed-sweep analysis is not
   invoked on adaptive recordings.

## Verification and evidence scope

The [evidence index](evidence/2026_09_09_adaptive_runtime/index.json) retains exact
source hashes, commands/static checks, final JUnit receipts, per-case source
counters and prior failed attempts. It contains no IQ or executable artifacts.

| Lane | Passing tests | Scope |
| --- | ---: | --- |
| Leo portable | 492 | Adaptive adapter/application/storage/publication/schedule/supervisor plus fixed capture, GLRT, history/API compatibility |
| PPU portable | 1,285 | Adaptive/fixed capture and current-main pilot/PSS/control/fine-schedule/source-support regressions |
| Scheduled native TCP | 12 | Both rates × shadow/adaptive × complete/cancel/pre-refill-cancel through scheduled application, concrete adapter, actual transport, queued store, publication and retry |
| Static | Passed | Ruff, whitespace, eight source modules checked with the actual Python-3.12 type target |

The four complete TCP cases each retain **2,480 full dual-RX visits** and
**2,480 correctly bound detector results**:

| Rate | Source span, samples | Uncompressed IQ verified per mode |
| --- | ---: | ---: |
| 2.5 MS/s | 750,209,920 | 5,952,000,000 bytes |
| 5 MS/s | 1,500,409,920 | 11,904,000,000 bytes |

Cancellation is requested after the thirtieth stored visit; already-delivered
complete visits are drained rather than discarded. The retained inventory and
the extra started/incomplete event are checked independently. Pre-refill
cancellation attests zero refills, zero retained IQ and zero detector results;
source elapsed time/duty and the UTC mapping remain unavailable. Each server
attests one open and one destruction. Retry verification occurs after its TCP
server has exited, proving that the existing recording does not require another
acquisition or a live radio context.

The source uses constant RX0, zero RX1, accelerated device time and a **1 ms
fixture guard**. Full spans are slightly longer than 300 seconds because the
last dwell finishes. Zero-RX1 detector results are unavailable, not absence
claims. These tests do not establish useful-signal sensitivity, original DMA
arrival behavior, ARM headroom, live RF duty or an adaptive scheduling gain.
The real acquisition-authority/SSH daemon lifecycle is represented by explicit
fixtures; its production controls were not exercised against hardware.

Portable tests separately cover changed source identity, malformed IQ, incorrect
visit order/inventory, missing restoration, unsupported metadata factories,
thread startup failure, timeout ownership, final draining, classification
snapshot failure, storage saturation, cleanup failure, cross-mode retries,
unpublished reservations, source counters above 2**53 and fractional offsets.
The existing Starlette/httpx deprecation remains visible in the test receipt.

## Failed attempts retained

- The initial synthetic PPU fixture omitted its target and hardware-prepared
  nonzero profile CRCs. Strict mapping rejected it; fixture values were corrected,
  not validation relaxed. Its accelerated 30-visit burst also exceeded an
  explicitly selected eight-visit storage queue. The adapter integration fixture
  now uses the existing scheduled 64-visit capacity; separate saturation tests
  still require explicit failure. This is not a runtime headroom adjustment.
- A readback assertion initially treated the public `(visit, CI16)` return value
  as an array. Correcting the test preserves exact dual-RX byte comparisons.
- The first four full scheduled TCP cases completed capture, publication,
  readback and retry but failed the final evidence annotation: the server stats
  object is a dictionary, not a path. JSON serialization fixes that harness bug;
  final tests are rerun. The unchanged 90 s server watchdog still excludes
  offline readback, as in the previous checkpoint.
- A proposed low-duty supervisor fixture initially requested an inadmissible
  guard. The corrected fixture models slow actual transitions with an unchanged
  admissible guard, testing the intended distinction between planned and
  observed duty. No acceptance threshold was lowered.
- Static checks caught two typing issues and formatting diagnostics, all fixed.
  No dependency pins, Python target, scientific golden fixtures or numerical
  tolerances changed to obtain a pass.

## Source and release state

Dedicated worktrees are retained. Freshly fetched Leo main `29be8492` is already
an ancestor. PPU main's independent `1245220` control/fine-start receipt changes
were reviewed and merged locally without conflicts at `5c15faf2`; their tests
are included above. libiio remains at the existing `42762db3` userspace provider
checkpoint, with no C change in this step.

Nothing in this checkpoint was pushed, merged into remote main or deployed.
The [full execution checklist](../docs/architecture/adaptive-scanner-implementation.md)
remains open. Next requirements are adaptive history/API/UI and actual-visit
analysis, fresh frozen held-out detector/policy qualification, the exact new
integrated 300 s ARM workload at both rates, separately authorized bounded RF
canaries, compatible remote merges/deployment and operational rollback checks.
Earlier worker timing and these synthetic TCP results do not replace those gates.
