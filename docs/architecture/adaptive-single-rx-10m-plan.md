# Adaptive single-RX 10 MS/s, 300-second scanner deployment plan

Status: host architecture accepted; integration and live qualification remain
open, 2026-09-13. This document does not change the running scanner.

Use only radio `104000bac4950008230026001b440a003a` at `192.168.1.17`
(`radio_pluto_003a`). Run 300-second scans on **ten-minute UTC start slots**.
Choose physical RX0 or RX1 once from the durable scan identity, retaining that
choice across retries. Migration is outside this change.

## Running baseline

Acquisition release `1212242843055e7e4079143ab1940532e8ac76fd` runs the qualified
fixed-order profile `single-rx-random-10m-300s-v1`. It records native 10 MS/s
CI16 with 10 MHz bandwidth, eight pilot-centred targets and 120 ms valid visits.
Keep 262,144-sample refills, 32 kernel buffers, read-ahead 8, writer queue 64,
a 1 ms transition guard and the existing single-thread math-library settings
as the starting point for adaptive qualification.

The [reboot recovery report](../../reports/2026_09_13_scanner_reboot_recovery/README.md)
records completed 17:30 and 17:40 scans at approximately 95.43% valid duty,
successful restoration, complete native-rate analysis and real-browser output.
This verifies fixed recording and publication, not adaptive feedback.

Analysis release `2bb4c3b1ec806b7c9181ff577a1c87387331f604` now uses four bounded
offline workers. Its first complete refinement/analysis/tracking cycle took
7:43.408, leaving about 77 seconds within the ten-minute cadence after the timer
pause. Scientific products matched two-worker replay exactly, and the concurrent
capture remained qualified. See the [analysis cadence report](../../reports/2026_09_13_analysis_cadence/README.md).

The host-wide acquisition lease can block a scheduled start while unrelated
radio work holds it. Preserve its ownership, pause and drain semantics. Do not
operate another radio or bypass the lease to qualify this profile.

## Accepted architecture

Record and analyze native **10 MS/s**. On the host, filter a separate copy of
each valid dwell to **2.5 MS/s**, screen all six 20 ms windows and perform at most
one ranked blind confirmation. The radio executes retunes and the existing
counter-authoritative adaptive policy. The acquisition producer alone owns IIO;
the computation worker never calls the radio or its socket.

The sealed filter is a causal 161-tap Q15 FIR, factor four, phase zero, reset
per visit. Group delay is 80 native samples (8 microseconds); output index
`k` has source centre `4*k - 80`. The first 40 outputs lack complete causal
support and are masked. Accepted candidates require valid fractional support.
Do not borrow history across retunes or receivers, drop a whole screen to hide
a boundary, or tune the frozen detector against holdout outcomes.

The current host worker bounds all outstanding jobs to two, including running
work and completed results awaiting consumption. It retains at most 9.6 MB of
queued/running CI16 input plus its DSP workspace. Conversion must preserve exact
CI16 values. Queue overflow, detector failure and expiration remain explicit
unknown/degraded outcomes; they cannot become evaluated negative detections.

See the [host-feedback design](adaptive-single-rx-10m-host-feedback-proposal.md)
for signal-time and feedback details. Host execution supersedes the earlier
on-radio proposal, whose full six-window pipeline missed the ARM timing gate.

## Current implementation evidence

- The sealed host DSP matches the independent same-coefficient scalar reference
  on all 64 reserved dwells. Both receivers and all eight targets are represented.
  The longer reference filter has the same 13 positive candidate outcomes;
  22 unknown-versus-negative differences retain explicit fractional-boundary
  uncertainty. These comparisons are not calibrated RF sensitivity or false-alarm
  measurements. Keep the seal and every original result.
- PPU commit `bcc68f1` adds explicit major-3 native-10M single-RX requests,
  actual-visit reconstruction, lifecycle checks and owner-thread feedback.
  Legacy fixed and adaptive V2 remain distinct. 1,172 targeted tests passed;
  later owner-thread/factory checks passed separately.
- libiio commit `ab89268` adds owned-buffer feedback, provider binding and
  native-10M policy admission for either RX. C and Python packets match byte for
  byte, including full uint64 source counters. Protocol, parser, transport and
  policy fault tests pass. Native and ARM builds succeed. These are development
  builds, not a source-pinned production bundle.
- Host paced replay uses saved recordings and the sealed detector, with a bounded
  worker and real feedback serialization. Preserve its exact source hashes,
  all rows, startup and steady-state timing, queue depth and memory evidence.
  Passing replay does not qualify live command/ack latency.
- Leo now has application-major-2 single-RX adaptive plans/receipts, a durable
  mode/configuration-bound intent, native single-RX manifests/readers/writers,
  provider-major-3 mapping and an acquisition-owner producer. Component tests
  cover both RXs, legacy storage compatibility, bounded decision overflow,
  rejected feedback, cancellation and restoration ownership. See the
  [capture integration checkpoint](../../reports/2026_09_13_host_adaptive_capture/README.md).
  Application capture-to-storage, native-rate analysis, resumable checkpoints
  and all three overview PNGs are now connected and tested through the analysis
  CLI. See the [native publication checkpoint](../../reports/2026_09_13_host_adaptive_analysis/README.md).
  Scheduler admission, refinement/tracking readers and API/UI still need
  integration. Do not enable an adaptive flag on the current fixed release.

## Critical path

| Stage | Work remaining | Exit evidence |
| --- | --- | --- |
| 1. Freeze host feedback integration | Bind the sealed DSP identity, complete paced replay, package compatible provider/PPU/native libraries. | Mean service time ≤90 ms, p99 ≤100 ms, feedback age ≤1 second, all six screens, no healthy overloads or growing queue; source and binary receipts. |
| 2. Connect capture through publication | Finish scheduler admission, refinement/tracking readers and API/UI; qualify saved-data throughput for the connected native analysis/PNG path. | Component, compatibility and saved-data tests pass for RX0 and RX1, with truthful actual visit timing and decision provenance. |
| 3. Qualify on the selected radio | Shadow RX0, shadow RX1, adaptive RX0, adaptive RX1, each bounded to 300 seconds. | Live gates below pass; stop on first failure and retain every attempt in the RF ledger. |
| 4. Deploy and verify | Switch one compatible release between scans, then verify its first scheduled scan. | Native recording, analysis and browser publication pass; ten-minute scheduling remains active and the fixed rollback is verified. |

## Application and persisted contracts

Add `adaptive-single-rx-random-10m-300s-v1` as an explicit profile. Bind mode,
physical RX, rates, bandwidth, detector/filter digest and operation identity in
the durable intent. Shadow and adaptive must not collide across retries. Preserve
existing UTC slot payloads; published major-version contracts remain immutable.

Use explicit new wire/application versions where geometry changes. PPU's
major-3 HOPR is 416 bytes; its source-bound HFB1 feedback is 160 bytes.
Unknown capabilities reject admission before capture. No unsupported adaptive
rate may silently fall through to a fixed capture labelled adaptive.

For either physical RX, the single payload channel is column zero. Carry the
physical receiver separately through source ports, mapping, manifests, readers,
analysis checkpoints, products and presentation. Store four CI16 bytes per time
sample, retaining actual target order and source-counter intervals. Eight
chronological visits in a storage chunk do not imply one uniform sweep.

Keep native-10M per-visit analysis and the existing scientific primitives.
Make the adaptive reader available to refinement and trajectory/TLE analysis;
do not introduce a second scientific implementation. Preserve explicit catalogue
or propagation failures rather than inventing matches. The complete native IQ
remains available for more exhaustive reanalysis.

Persist host decision coverage, filter support, numerical evidence, health,
timing and feedback acceptance separately from later HOPS policy application.
A computed result is not automatically applied: the source may have ended.
Show recording rate 10 MS/s, decision rate 2.5 MS/s, host execution, selected RX,
valid duty, allocation, revisit gaps, feedback freshness and fallback reason.
Generate and source-bind coverage, GLRT/CFO, refinement and tracking assets.

## Policy and fault semantics

Preserve the existing policy unchanged:

- Three uniform warmup visits per target, reset each scan.
- A positive promotes immediately; active-to-quiet weight is 3:1.
- Demotion requires three evaluated consecutive misses and two seconds since
  the last positive source dwell ended. Unknown breaks the miss streak.
- All eight targets retain exploration with the planned three-second revisit
  limit. Measure actual lateness and starvation.
- Results bind session, policy generation, stream generation, physical RX,
  target, source event/visit, valid counters and detector/filter configuration.
  Apply in source order; expire after one second of device sample time.
- Three unhealthy/missing/expired results or an explicit feedback fault latch
  uniform scanning for the rest of the scan. Preserve the fallback reason.

Host monotonic time measures processing latency; device counters govern source
age and policy application. A source-ending tail result is explicitly unapplied.
Unknown observations and intentional skips are not evidence of signal absence.
Healthy qualification may not rely on skipping decisions.

## Tests before RF

Every changed component owns tests. Cover both physical receivers, old contract
decoding, byte/sample accounting, source hashes, cancellation/restoration, counter
extension across 2^32 and beyond exact float integer range, stale/duplicate/
reordered/foreign feedback, worker failure, bounded queues, checkpoint resume,
and API/PNG manifest binding. Exercise all target masks and policy transitions.

Saved recordings establish numerical parity and processing capacity. They cannot
establish what signal would have existed at hypothetical adaptive revisit times.
Do not infer adaptive sensitivity or allocation benefit from counterfactual IQ.

## Live qualification and RF budget

Keep the existing cumulative ledger. It has charged 237.331441 seconds, leaving
1,562.668559 seconds of the 30-minute qualification allowance: 1,500 seconds are
reserved for four canaries and the first scheduled verification, leaving only
62.668559 seconds unreserved. Count partial failed attempts. Do not start an
unbudgeted baseline or retry, overlap another capture on the selected radio, or
launch a multi-hour qualification campaign. Normal continuous production
scheduling is separately authorized by the user.

Freeze these live gates before testing:

- Zero lost samples, overflows, lost events or receiver-binding errors; full
  nominal duration and verified restoration.
- At least 95% valid-sample duty, with no more than 0.5 percentage-point regression
  against the representative fixed baseline. Duty uses the attested source span,
  including transitions; it is distinct from the ten-minute start schedule.
- No overload skips, expired decisions, sustained backlog or unexplained fallback
  in healthy runs. Every accepted feedback result respects the one-second gate.
  Injected faults demonstrate the expected uniform fallback.
- Policy decisions match the independent model; revisit misses remain visible.
- Native-rate analysis and applicable UI assets keep up with the ten-minute
  cadence. Browser images decode, source hashes agree, RX labels are correct,
  and historical recordings remain viewable.

## Switch and rollback

Pin and stage the compatible Leo, PPU, libiio, native detector, template and
filter artifacts through normal release qualification. Preserve current
selectors and environment before changing them. Switch acquisition and its
dependent analysis/API readers between scans after the canaries pass; do not
modify immutable release files.

Verify the first scheduled adaptive scan through native analysis and real browser
output within the reserved budget, then leave normal ten-minute scheduling active.
If a gate fails, stop new adaptive starts, restore the complete previous release
and `single-rx-random-10m-300s-v1`, check restoration/service health and retain all
evidence. Uniform fallback within a scan protects capture but does not qualify
an adaptive deployment. No firmware flash or corpus migration is planned.

Done means the scheduled random-RX adaptive profile completes capture, native-10M
analysis and web publication while satisfying these gates. The immediate next
implementation step is scheduler admission and runtime packaging for the new
capture/analysis path. API/UI integration and refinement/tracking readers now
pass component tests, with all three native PNGs decoded in Chromium for both
physical receivers using synthetic captures. Saved-data throughput checks and
live qualification remain required; see `reports/2026_09_13_host_adaptive_web.md`.
