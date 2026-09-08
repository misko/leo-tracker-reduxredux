# Single-RX ARM presence detector: implementation and qualification plan

## Current goal revision — frame-carried dwell classification

The user has superseded the earlier advisory-side-channel goal with:
**implement a realtime scanner GLRT classification that identifies which
scanner dwells contain Starlink signal and reports it in LIBIIO frame data,
without reducing scanner duty percentage.**

The native numerical and worker checkpoints below remain reusable foundations,
not completion of this revised goal. The final transport is now a negotiated,
versioned extension carried with LIBIIO frame metadata, not a separate result
connection. The proposed 0.5-percentage-point duty allowance is withdrawn.

Additional mandatory requirements:

- Qualify the classifier against the entire retained 120 ms dwell. A negative
  first-20ms probe is insufficient. Evaluate inexpensive timing proposals over
  all six temporal slices followed by bounded fractional GLRT confirmation,
  preserving the one-selected-RX constraint. This is an experiment, not an
  assumed sixfold speedup or sensitivity result. Keep the frozen 20 ms detector
  as a comparator, not the final whole-dwell classifier.
- Calibrate and evaluate a Starlink classification decision, separately from
  numerical candidate agreement. Use development/holdout separation, known
  pilot and interference controls, and explicit unresolved RF cases. Carry the
  score, coverage, algorithm/configuration identity, and failure reason; never
  convert incomplete computation into an absence claim.
- Emit completed classifications in subsequent LIBIIO frames, explicitly
  referring to their original session, visit, RX, and sample-counter interval.
  Never wait for GLRT before forwarding current IQ. A negotiated metadata-only
  terminal frame must deliver final results after RF capture stops; it must not
  fabricate IQ or rely on an old client treating a zero-IQ frame as ordinary data.
- Preserve existing ABI-3 base metadata and HOPS/HOPT published contracts. Add
  an opt-in envelope/version and negotiate capacities and terminal semantics.
  Old clients retain byte-identical framing. New clients without support
  continue recording with an explicit unavailable-classification state.
- Require no reduced dwell length, increased RF gaps, dropped IQ, or delayed
  hop scheduling. Qualify capture-path replay and matched live disabled/enabled
  runs against the unchanged scanner. Report duty measurements and uncertainty;
  no positive regression allowance is accepted as success. Extra result drain
  after capture is measured separately from the device-counter duty denominator.

Concrete integration entry points inspected read-only: the pinned userspace
iiOD provider in libiio `c752ab684a4c9924ee362ccfb02a7ac65f7992f9` builds ABI-3
metadata plus HOPS in `iiod/spf-buffer-metadata.c`; `iiod/ops.c` transports a
length-delimited metadata record followed by IQ. Its exact-gap parser and the
`pluto_plus.hardware.iio_metadata.IioRawSidecarCaptureSession` / persistent-hop
decoder validate current lengths and geometry, so appending bytes without
explicit negotiation would break compatibility. Those parsers, all transport
modes used by the scanner, and final-frame draining need owned tests.

Status: implementation in progress, 2026-09-08. This document authorizes no
deployment or new RF collection. Production scanning and scientific analysis
remain unchanged. The [native checkpoint report](../../reports/2026_09_08_arm_presence_native_checkpoint.md)
records baseline parity and ARM measurements. The newer
[power-proposal checkpoint](../../reports/2026_09_08_arm_presence_power_checkpoint.md)
meets the 100 ms saved-IQ CPU target for one separately named single-candidate
variant, but broader quality and streaming gates have not passed.
The latest [differential/tone checkpoint](../../reports/2026_09_08_arm_presence_differential_checkpoint.md)
flags all 20 development reference positives, associates 19/20, and measures
51.7/99.2 ms warmed p99 CPU on 800 CI16 ARM replays. First-execution/tail
latency, fresh holdout, temporal coverage, and streaming qualification remain
open in that earlier checkpoint. The newer
[worker/holdout checkpoint](../../reports/2026_09_08_arm_presence_worker_checkpoint.md)
adds 576 held-out probes, an isolated worker/collector, and two 300 s repeated-
probe ARM loads with 4,762/4,762 desktop-matching results and no losses. CPU p99
is 53.0/100.32 ms: the strict 5 MS/s CPU gate still misses. Original DMA/metadata
arrival replay, iiOD/host/UI integration, and live shadow qualification remain
unfinished; nothing has been deployed. First-window reference evidence covers
only 15/35 visits with reference evidence somewhere in the six-window tiling.

The newer [whole-dwell screen/frame checkpoint](../../reports/2026_09_08_arm_presence_window_rank_checkpoint.md)
adds the C/Python envelope and fault-isolated host binding (not actual LIBIIO
transport integration), plus a six-window native ranking experiment. Its
smallest grid costs 20.0/40.01 ms p99 ARM CPU for the complete 120 ms screen;
1,000 optimized saved-IQ/control outputs match desktop exactly. The best tested
single-window ranking associates 20/35 development reference-positive dwells,
versus 15/35 for the first window; top three reaches 28/35, versus 30/35 for all
six existing confirmations. Neither quality nor combined confirmation cost is
qualified. Next: measure proposal reuse inside bounded fractional confirmation,
without assuming that screen coverage alone establishes an absence verdict.

The [whole-dwell confirmation checkpoint](../../reports/2026_09_08_arm_presence_dwell_confirmation_checkpoint.md)
now measures combined execution and tests proposal reuse. A two-resolution
seeded policy reaches roughly 90 ms p99 CPU at 5 MS/s after exact dependency
pruning, but associates only 18/35 development-positive dwells with one
confirmation versus 20/35 for blind confirmation. Keeping the stronger blind
search costs about 110 ms p99, still above target. Integer folding and screen
dependency pruning preserve 2,304 complete candidate structures in desktop
replay; 288 final ARM confirmation windows match the original desktop. These
are engineering improvements, not classifier quality or streaming passes.

## Objective and boundaries

Evaluate one selected RX during each 120 ms valid scanner visit, initially using
the first 20 ms and the existing two-candidate fractional GLRT path. Aim for
100 ms of detector CPU per incoming visit at both 2.5 and 5 MS/s, while preserving
dual-RX recording and approximately 126 ms visit spacing.

The existing prototype produces **GLRT candidate evidence**, not a verified
Starlink verdict. The revised end state requires qualified dwell classification
as specified above. A missed check is unknown, not negative. Neither a negative score nor
worker failure may discard IQ, shorten a capture, suppress normal analysis, or
change hopping, gain, bandwidth, firmware, FPGA, or kernel behavior.

Use archived IQ first. Exclude radio serial
`104000bac4950008230026001b440a003a` from every hardware action. Use an
identity-attested, idle, non-production radio over its `192.168.1.*` interface
for ARM replay; do not assume an address identifies a device. If no safe device
is available, report that checkpoint as blocked rather than load production.

## Evidence and unresolved questions

- Latest prototype: differential/power timing proposals, all-symbol CFO
  acquisition, and explicitly reported stationary-tone conditioning. Iterative
  FP64 FFT and exact widening CI16/NEON lag sums bring warmed p99 to 51.7/99.2 ms
  at 2.5/5 MS/s. All 800 ARM outputs match desktop, but 5 MS/s CPU maxima reach
  102.1 ms warmed and 109.6 ms first execution. This is not a streaming pass.
  The remaining CFO mismatch and additional unresolved RF flags are retained;
  tone-control improvement is development evidence, not specificity proof.
- Latest reduced-work result: a single-candidate 4096-bin pilot-power proposal
  with original-IQ fractional confirmation takes 43.5/77.4 ms warmed p99 CPU
  at 2.5/5 MS/s in 640 native-CI16 replay executions. Wider development recovers
  8/8 and 9/12 reference-associated positives, respectively, with timing misses,
  a CFO alias, and tone false positives still unresolved. This is not a
  qualified every-visit detector or authorization to proceed to live deployment.
- The native checkpoint now contains actual saved-IQ ARM smoke measurements.
  Initial total CPU was 4.8/15.6 seconds at 2.5/5 MS/s, reduced to approximately
  3.0/8.8 seconds by the first equivalent-computation optimization pass. These
  are not streaming qualifications or timing distributions. They supersede
  any earlier assumed desktop-to-ARM slowdown factors.
- A separately configured FP32/NEON coarse-search experiment now reduces smoke
  totals further to approximately 1.55/4.40 seconds, with original fractional
  candidate tolerances passing on the tested inputs. This remains above budget;
  it is neither the default oracle nor a qualified every-visit detector.
- [Desktop screen](../../reports/2026_09_07_arm_presence_desktop_screen.md):
  reduced GLRT is implemented and timed on x86, not ARM. Approximate single-RX
  median detector CPU is 28 ms at 2.5 MS/s and 68 ms at 5 MS/s, excluding the
  separately measured input conversion.
- [Current scanner audit](../../reports/2026_09_07_current_scanner_timing_audit.md):
  120 ms valid visits, approximately 126 ms start-to-start, dual-RX recording.
- Read-only inspection on 2026-09-08 found two online ARMv7 Cortex-A9 cores,
  NEON support, and no Python runtime on the scanner radio. This is not a
  measurement of free CPU capacity, CPU frequency, or detector speed, nor an
  attestation of a future replay radio.
- GLRT2 still searches the full coarse timing/CFO grid. It limits subsequent
  candidate refinement to two; it does not perform just two correlations.
- The current 5 MS/s GLRT accepted synthetic tone controls. Numerical parity
  must preserve and report this limitation; it must not be mistaken for
  detector-specificity qualification.
- Previously examined held-out excerpts are now historical evidence. Do not
  reuse them as an untouched holdout for a newly tuned detector or RX choice.

This plan deliberately measures ARM runtime before completing specificity work:
runtime replay is an engineering experiment, not authorization to gate capture.
That updates the ordering suggested in the older desktop report without
weakening its scientific warning.

## Proposed architecture

1. Existing iiOD remains the sole acquisition/buffer owner and forwards both RX.
2. A small probe collector copies only the selected RX and counter-attested
   valid sample interval into preallocated storage. It never retains a DMA
   buffer for the duration of a detector job.
3. An isolated native worker consumes probes asynchronously. A bounded shared
   buffer pool and notification mechanism separate it from capture. No IIO
   device handle or radio-control authority passes to the worker.
4. Completed classifications enter a bounded result ring. A negotiated,
   versioned LIBIIO frame-metadata extension carries completed results from
   earlier dwells without waiting for computation or opening another RX buffer.
   A terminal metadata-only frame drains results after RF capture stops.
5. The host maps results through a narrow adapter into a new advisory evidence
   product. Existing IQ, HOPS/HOPT, metadata, and published analysis contracts
   remain byte-compatible and semantically unchanged.

Three CI16 probe slots contain 0.6 MB at 2.5 MS/s or 1.2 MB at 5 MS/s of 20 ms
single-RX data. The current fixed-size prototype reserves the maximum at both
rates: 1,234,944 bytes including the result ring and bookkeeping. Detector
scratch space is additional; the two-workspace ARM worker showed 19,260 KiB
RSS high water during the 5 MS/s run, not a final peak-memory qualification.
Buffer states must distinguish filling, queued, and in-use; capture must never
overwrite an in-use slot. Overflow increments explicit counters and drops
detector work, not recording data.

The frame envelope and terminal frame are proposed custom iiOD/libiio
extensions, not existing stock APIs. Keep result batches bounded and
nonblocking with respect to capture. Preserve legacy IQ framing through
explicit capability/version negotiation; do not silently append fields to an
immutable published contract.

## Checkpoints

### C0 — Freeze the experiment and interfaces

Deliverables:

- A clean implementation worktree based on freshly fetched remote main; record
  the exact revision and reconcile the existing local research files explicitly.
  Do not overwrite the current worktree or implicitly include unrelated work.
- A manifest of existing IQ slices, source hashes, selected RX, rates, edges,
  probe offsets, cold-search settings, controls, and numerical tolerances.
- A fixed RX selected on development evidence, with no combining, fallback, or
  automatic switching to the other RX during evaluation.
- A minimal detector interface: immutable samples plus rate/edge geometry in;
  bounded candidate evidence and execution status out. No storage, HTTP, IIO,
  PostgreSQL, or Python dependency inside the native numerical library.

Tests and exit gate:

- Reproduce saved GLRT2 candidates and the known tone counterexample.
- Verify archive access is read-only and all probes exclude transition spans.
- Freeze tolerances before examining native output. Reuse reviewed numerical
  tolerances where available; explicitly review any new ones. Never regenerate
  a golden fixture merely to make the port pass.
- Stop if the source algorithm, selected RX, or sample geometry is ambiguous.

### C1 — Faithful native implementation on desktop

Deliverables:

- A small C numerical library and standalone replay executable. Port only the
  cold acquisition, two retained candidates, refinement, and exact/control
  scoring needed by GLRT2, not the full Standard analysis application.
- Reuse the existing coarse C kernel where possible. Preserve the scientific
  search grid and fractional sampling; an optimized execution layout must not
  add or remove searched hypotheses.
- Keep a faithful precision baseline. Allocate workspace and prepare templates
  outside steady-state execution, with startup costs reported separately.
- Stage timings for input conversion, coarse search, candidate selection,
  CFO refinement, fractional timing, final scoring, and total execution.

Tests and exit gate:

- Differential tests against the Python/NumPy oracle for both rates and edges:
  candidate inventory, ordering, epochs, CFOs, support, scores, and gate decisions.
- Synthetic tests: zeros, noise, tones, clipping, fractional delays, grid-edge
  CFOs, weak/strong signals, ties, truncated input, and invalid geometry.
- Tests for counters above 2^53, integer-delta-first arithmetic, non-integer
  frame periods, and separate fractional offsets. Do not reintroduce rounded
  frame-period drift or cross-retune carrier-phase continuity assumptions.
- Sanitizers, bounded allocations, overflow checks, repeated initialization,
  and deterministic teardown. Existing component regressions must still pass.
- Exit only with reviewed parity. A faster but numerically different detector
  becomes a separately named experiment, not a replacement baseline.

### C2 — Paired ARM timing, without RF

Deliverables:

- Cross-build the same library as an ordinary temporary ARM userspace binary.
  Do not install Python, modify the root filesystem, restart acquisition, or
  flash anything. Attest the exact target serial and its existing SSH key.
- Replay identical saved probes on desktop and the idle ARM radio, one worker,
  with matched settings. Separate file transfer/loading from detector timing.
- Record binary/source hashes, compiler flags, CPU identity, online cores,
  available clock information, affinity, load, CPU/wall times, and peak memory.
  Do not infer clock speed from BogoMIPS or treat a second core as reserved.
- Compare three columns: current Python/native desktop path, portable native
  desktop path, and identical native ARM path. This separates implementation
  gains from processor differences.

Tests and exit gate:

- Begin with a small smoke batch, then a bounded replay covering both rates and
  edges, signal-bearing examples and controls. Limit each invocation with a
  watchdog and CPU/memory bounds; do not start an open-ended benchmark.
- Check ARM output parity before interpreting timings. Report cold-start and
  warmed distributions separately, including p50/p95/p99/max and paired ratios.
- Target p99 total detector CPU <=100 ms per checked visit, including conversion.
  Report observed maxima; a small-sample p99 is not a worst-case guarantee.
- This checkpoint yields measured feasibility, not streaming qualification. If
  it misses the target, proceed only with offline optimization, not deployment.

### C3 — Optimize measured bottlenecks and retest quality

Try changes individually, in this order:

1. Reuse scratch space, templates, FFT plans, and rotation tables; remove
   repeated conversions and unnecessary copies without changing mathematics.
2. Optimize the coarse search using measured profiling results.
3. Evaluate single-precision/NEON arithmetic against the faithful baseline;
   explicitly check near-threshold decisions and weak signals. Keep full
   integer counters and separately represented fractional timing.
4. Only if needed, evaluate fewer frames, shorter probes, or every-Nth revisit
   as separately configured algorithms with measured sensitivity tradeoffs.

Tests and exit gate:

- Re-run numerical, ARM timing, and development-quality tests after each change.
- Freeze revised thresholds/settings before opening fresh held-out scans.
- Measure single-RX agreement with the dense fractional reference, separately
  from genuine specificity evidence. Include tone, colored-noise, wrong-pilot,
  and available real-interference controls on both edges and rates. Report
  uncertainty and scan-level dependence, not just pooled window percentages.
- Do not choose a gate solely to reject the already-known tone example.
- Failed cache reuse remains an optional research direction, not an assumed
  speedup or dependency for the first release.
- If only every-Nth revisit fits, report the reduced check coverage explicitly;
  do not call it every-visit qualification. Schedule fairly per channel/edge,
  avoiding global modulo choices that repeatedly select only one target.

### C4 — Streaming replay and failure isolation

Deliverables:

- A replay harness delivering archived blocks with their original sample
  counters, transitions, and arrival cadence through the proposed collector.
- An isolated worker with preallocated probe slots, bounded result retention,
  observable queue depth, processing age, skipped counts, and explicit shutdown.
- Bounded 300 s paced replays at each rate on the idle ARM target. No RF is
  opened. These measure detector scheduling, not actual DMA/network headroom.

Tests and exit gate:

- Arbitrary DMA/dwell boundaries, split probes, startup/retune guards, delayed
  metadata, counter gaps, partial final visits, cancellation, and rate changes.
  Unknown/invalid intervals must never silently become valid detector input.
- Slow worker, process crash, malformed result, full queue, stale session,
  duplicate result, disconnected consumer, and shutdown with work pending.
- No blocking waits in capture submission, no DMA buffer held by the worker,
  no unbounded memory, no silent overwrites, and correct counter association.
- Normal every-visit mode: zero skipped valid probes, no growing queue or
  end-of-run backlog, p99 CPU <=100 ms, and measured wall-time tails compatible
  with the actual arrival sequence. A bounded queue alone does not prove success.
- Stress mode: explicit skipped/unknown evidence is acceptable; capture/replay
  delivery must remain unaffected. Tail latency must be reported separately
  from throughput, especially when late hop evidence delays probe eligibility.

### C5 — Versioned iiOD/host integration, still no live change

Deliverables:

- An opt-in classifier capability and bounded result batches in a newly
  versioned LIBIIO frame envelope. Preserve existing metadata and hop wire
  formats for legacy negotiation.
- A new evidence contract binding session/generation, result sequence, visit,
  RX, rate, channel/edge, input counter bounds, algorithm/configuration identity,
  candidate fractional timing/CFO/scores, execution times, and status.
- Sequence semantics for pending results, overflow, duplicate delivery,
  restart, terminal completion, and bounded metadata-only final drain. Scope
  access to the owning session;
  stale or unrelated sessions must not read another session's results.
- A host adapter and independent advisory storage/UI representation. Late or
  missing detector evidence must not block recording publication or analysis.
- The native library is owned and tested with the analyzer; iiOD consumes a
  pinned build artifact through the narrow interface. No reference repository
  or another component's private implementation becomes a runtime dependency.

Tests and exit gate:

- Golden protocol round trips, malformed/oversized packets, sequence gaps,
  reconnects, overflow notices, and late results attached to their original visit.
- Old-client/new-daemon and new-client/old-daemon compatibility. Unsupported
  capability falls back to normal recording, not failed acquisition.
- Audit strict capability/ABI checks and exact-field validators before adding
  discovery fields; extension negotiation must not break existing preflights.
- Classification delivery must not OPEN another RX buffer or change channel
  masks. Results arriving after their original IQ frame must still map exactly
  to their source dwell; terminal results cannot disappear at stream EOF.
- Worker lifecycle tests cover crash, timeout, parent exit, and cleanup of only
  its own resources. Do not weaken the existing process-identity/ownership checks.
- Host tests use declared PostgreSQL/hardware/corpus markers where required,
  with unavailable dependencies reported explicitly rather than silently skipped.

### C6 — Authorized live shadow verification and deployment checkpoint

Prerequisites: C0-C5 passed, exact artifact review, a safe target reserved, and
explicit user authorization for any new RF collection. No firmware/FPGA change.

Procedure and tests:

1. Run a short disabled/enabled shadow comparison on a non-production,
   serial-attested radio over its LAN endpoint; then bounded 300 s checks at
   both rates if the smoke test passes. The entire authorized RF campaign must
   remain <=30 minutes and must not displace production recording.
2. Preserve raw dual-RX capture throughout. Measure actual CPU/IRQ contention,
   queue age, detector coverage, valid duty, retune latency, overflows, missing
   samples, restoration, and result-to-IQ alignment.
3. Revised gate: zero missing samples/overflows, no failed restoration, normal
   every-visit classifier coverage, and no scanner-duty reduction against a
   matched classifier-disabled baseline. No positive duty-regression tolerance
   is authorized. Report measurement uncertainty and the hop-latency
   distribution; do not hide regressions behind rounded mean percentages.
4. Test worker failure and host disconnection without changing capture policy.
   Keep controls labelled as advisory GLRT evidence while specificity is unresolved.
5. Prepare an opt-in release with pinned binaries and a tested rollback. Merge
   and production deployment are separate approval checkpoints, not implied by
   approval of this plan. Default enablement follows successful shadow review.

## Completion and reporting

Each checkpoint produces a compact receipt: source/binary identity, inputs,
commands, tests, measurements, limitations, and pass/fail decision. Failed gates
retain evidence and return to the smallest relevant earlier stage; never adjust
golden data or silently relax success criteria.

The final report must distinguish:

- Numerical parity versus independent signal evidence.
- Desktop measurements versus actual ARM measurements.
- Detector CPU versus wall latency and shared-system overhead.
- Checked-probe coverage versus RF recording duty.
- Offline replay feasibility versus live streaming qualification.

**Next milestone: qualify whole-dwell classification and implement negotiated
frame-metadata delivery, with unchanged RF duty.** The native numerical
baseline, ARM timing comparisons, holdout experiment, and isolated handoff now
exist. The 300 s repeated-probe runs are a scheduling experiment, not the
required original block/counter/metadata-arrival replay or live headroom test.
Finish those checks and versioned C5 integration before deployment or live RF.
