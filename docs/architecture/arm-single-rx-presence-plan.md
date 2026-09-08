# Single-RX ARM presence detector: implementation and qualification plan

Status: proposed, 2026-09-08. This document authorizes no deployment or new RF
collection. The scanner and scientific analysis remain unchanged.

## Objective and boundaries

Evaluate one selected RX during each 120 ms valid scanner visit, initially using
the first 20 ms and the existing two-candidate fractional GLRT path. Aim for
100 ms of detector CPU per incoming visit at both 2.5 and 5 MS/s, while preserving
dual-RX recording and approximately 126 ms visit spacing.

The product is initially **GLRT candidate evidence**, not a verified Starlink
verdict. A missed check is unknown, not negative. Neither a negative score nor
worker failure may discard IQ, shorten a capture, suppress normal analysis, or
change hopping, gain, bandwidth, firmware, FPGA, or kernel behavior.

Use archived IQ first. Exclude radio serial
`104000bac4950008230026001b440a003a` from every hardware action. Use an
identity-attested, idle, non-production radio over its `192.168.1.*` interface
for ARM replay; do not assume an address identifies a device. If no safe device
is available, report that checkpoint as blocked rather than load production.

## Evidence and unresolved questions

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
4. Completed evidence enters a bounded result ring. An optional, versioned
   command on a separate control connection to the existing iiOD port returns
   results by session and sequence cursor, without opening an RX buffer.
5. The host maps results through a narrow adapter into a new advisory evidence
   product. Existing IQ, HOPS/HOPT, metadata, and published analysis contracts
   remain byte-compatible and semantically unchanged.

Three CI16 probe slots require 0.6 MB at 2.5 MS/s or 1.2 MB at 5 MS/s for 20 ms
single-RX probes. Detector scratch space is additional and must be measured.
Buffer states must distinguish filling, queued, and in-use; capture must never
overwrite an in-use slot. Overflow increments explicit counters and drops
detector work, not recording data.

The result-read command is a proposed custom iiOD extension, not an existing
stock libiio API. Prefer it over changing IQ framing or polling a latest-score
attribute that can lose visit association. Keep replies bounded and nonblocking
with respect to capture. A future metadata envelope is a separate design change.

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

- An opt-in detector capability and bounded result-read operation on the
  existing daemon. Preserve all published metadata and hop wire formats.
- A new evidence contract binding session/generation, result sequence, visit,
  RX, rate, channel/edge, input counter bounds, algorithm/configuration identity,
  candidate fractional timing/CFO/scores, execution times, and status.
- Cursor semantics for no data, overflow, duplicate reads, restart, terminal
  completion, and bounded final drain. Scope access to the owning session;
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
- The control connection must not OPEN another RX buffer or change channel masks.
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
3. Proposed gate: zero missing samples/overflows, no failed restoration, normal
   every-visit detector coverage, and no more than 0.5 percentage points of
   valid-duty regression against a matched detector-disabled baseline. Freeze
   that regression tolerance before the comparison; investigate material hop
   latency increases even if mean duty passes.
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

**First implementation milestone: C0-C2, a parity-tested native GLRT2 replay and
an honest measured desktop-to-ARM comparison. Do not build live integration
before that experiment tells us it is worth doing.**
