# Counter-authoritative Pluto capture continuity plan

Status: implementation authorized on 2026-08-24  
Evidence baseline: [`reports/2026_08_24_refill_continuity_loopback.md`](reports/2026_08_24_refill_continuity_loopback.md)

## Objective

Make every new live dwell and scanner capture able to prove whether its returned
IQ is continuous on the Pluto FPGA sample clock.  When samples are missing, the
system must preserve the observed IQ, record the exact gap, expose a masked
device-time-aligned view with logical zero filling, and make the integrity loss
impossible to miss operationally or scientifically.

This plan covers five required behaviors:

1. Detect discontinuities from the FPGA counter attached to each refill.
2. Stitch observed refills on the device-sample axis and logically zero-fill
   exact missing ranges.
3. Emit an immediate error and persist a degraded integrity result for every
   missing sample.
4. Destroy and recreate receive buffers before every dwell capture and every
   independently tuned scanner target.
5. Configure and verify a nontrivial receive queue, initially eight kernel
   buffers, while keeping the radio drain independent of compression and
   storage latency.

## Non-negotiable semantics

- `session_sample_start` remains the coordinate of bytes actually stored in the
  immutable observed-IQ payload.  It is never relabeled as a device coordinate.
- `device_sample_counter` is the authority for sample-time continuity.
- Host timestamps and host-generated indexes may bound an event but may not
  certify sample continuity or synthesize an exact missing count.
- Zero filling is a coordinate/view operation, not signal recovery.  Every
  zero-filled span carries a false validity mask and a continuity-segment
  boundary.
- Phase, frame timing, trajectory replay, carrier tracking, Doppler fitting,
  and Kalman state never bridge a missing span merely because a dense reader
  returns zeros there.
- Existing published V1 contracts and recordings remain readable and
  immutable.  New fields that change persisted meaning use additive V2
  contracts or immutable sidecar products.
- A clear overflow flag is not evidence of continuity.  The controlled K=1
  experiment had 572 counter gaps and zero overflow flags.

## Evidence and initial production values

The controlled dual-RX test used 2.5 MS/s and 131,072 samples per refill.

| kernel buffers | counter gaps | missing samples | stored span | FPGA-counter span |
|---:|---:|---:|---:|---:|
| 1 | 572/572 | 75,759,616 | 30.0417024 s | 60.3455488 s |
| 2 | 0/572 | 0 | 30.0417024 s | 30.0417024 s |
| 4 | 0/572 | 0 | 30.0417024 s | 30.0417024 s |
| 8 | 0/572 | 0 | 30.0417024 s | 30.0417024 s |

Two buffers are only the observed minimum for that host load and refill size.
Production starts at eight.  A normal dual-RX dwell refill contains 262,144
sample times and occupies 2 MiB as CI16.  Eight kernel buffers therefore use 16
MiB per radio and cover about 0.839 seconds of nominal sample time.  A 32-refill
userspace queue adds 64 MiB per radio.  Two production radios therefore need
about 160 MiB for kernel and userspace receive buffering together.

Neither queue is a substitute for adequate sustained throughput.  If the
storage consumer is slower than live RF on average, capture must fail visibly
rather than silently compress time.

## Target architecture

```text
firmware counter + refill metadata
               |
               v
metadata-capable upstream radio port
               |
               v
shared counter/sequence validator
               |
               v
high-priority refill producer -> bounded RAM queue -> storage consumer
               |                                      |
               +---------- observed IQ ---------------+
               +---------- immutable gap map ----------+
                                                          |
                                                          v
                                  masked device-time reader
                               observed IQ | logical zeros
                                                          |
                                                          v
                           gap-aware Standard/scanner analysis
```

## Workstream A: metadata-capable Pluto port

The pinned `pluto-plus-utils` receive port must expose one returned object that
atomically binds IQ to the metadata header delivered with that refill:

- `first_sample_sequence`
- `buffer_sequence`
- metadata stream/generation ID
- metadata flags
- sample-time realtime estimate and uncertainty, when present
- the exact sample count and receiver geometry

The port must attest the metadata ABI and require a valid hardware-counter flag
before advertising counter support.  The ordinary `.rx()` path remains
available only as an explicitly continuity-unobservable legacy path; it is not
accepted for new production science capture.

Required lifecycle operations:

```text
open -> configure -> destroy_rx_buffer -> set_kernel_buffers(K)
     -> verify K -> begin_metadata_capture -> refill* -> close
```

Changing the refill size, tuning, receiver set, sample rate, or stream
generation invalidates the current continuity chain and requires a fresh
`begin_metadata_capture`.

## Workstream B: shared validation and fail-loud behavior

One component-owned validator is used by the radio adapter and rerun by the
storage writer.  For adjacent blocks in one stream generation:

```text
expected_counter = previous_counter + previous_sample_count
counter_gap       = current_counter - expected_counter
```

Classification:

- `counter_gap == 0` and sequence increments by one: contiguous.
- `counter_gap > 0`: `GAP_BEFORE` with the exact missing count.
- counter duplicate, regression, impossible wrap, sequence regression, stream
  generation change without reset, bad header, or counter/sequence
  disagreement: hard integrity error.
- an overflow flag without a positive counter gap is still persisted and
  begins a new continuity segment.

The first valid block establishes a baseline but cannot prove what happened
before capture start.  A new capture never attempts to join to a previous
capture.

Every discontinuity immediately produces:

- a structured error log containing radio, stream, expected and actual
  counter, missing samples, and missing duration;
- an acquisition-integrity metric and alert;
- a persisted gap/overflow count and exact missing total;
- a partial/degraded recording outcome rather than a normal continuous result;
- a red integrity banner in presentation;
- an explicit analysis reset at the gap.

`sample_loss_observable=true` means that the complete stored counter chain was
independently validated, not merely that first and last counters were present.

## Workstream C: reset and buffer policy

### Dwell capture

1. Open and attest the radio.
2. Destroy any previous userspace RX buffer.
3. Apply tuning, sample rate, bandwidth, channels, and gains.
4. Set `kernel_buffers=8` and verify exact readback before buffer creation.
5. Perform configured settling/priming.
6. Destroy the priming buffer and begin a fresh metadata capture at the
   readiness gate.
7. Establish a new counter baseline from the first accepted refill.

### Scanner target

Every retuned target is a separate capture episode:

1. Destroy the preceding target's RX buffer.
2. Tune the LO and verify readback.
3. Wait the configured tuning-settle interval.
4. Set and verify `kernel_buffers=8`.
5. Create a fresh metadata buffer only after tuning.
6. Capture the target frame and persist its independent counter evidence.
7. Destroy the buffer before the next retune.

No cross-retune sample continuity is claimed.  The reset order prevents a deep
queue from returning samples captured at the previous LO.

Persisted configuration changes use additive `CaptureProfileV2`,
`CapturePlanV2`, `ScannerConfigurationV2`, and scanner IQ frame/manifest V2
contracts.  V1 remains accepted for replay/import but is not the live default.

## Workstream D: refill producer and storage consumer

The current dwell loop synchronously performs radio refill, conversion,
compression, shard close, rename, and `fsync`.  Replace it with:

- one producer per radio whose critical path is refill, metadata validation,
  CI16 conversion if unavoidable, and nonblocking enqueue;
- one bounded queue per radio, initially 32 refills;
- an independent consumer that owns compression, hashing, timeline writing,
  shard finalization, rename, and `fsync`;
- persisted or reported queue capacity, high-water mark, enqueue failures, and
  maximum refill service interval.

Queue full is a terminal integrity error.  The producer must not block and then
resume with an apparently contiguous stored stream.  The partial recording is
sealed with the last validated counter and failure reason when safe.

The requested dwell duration is defined on the device-counter axis.  If a gap
occurs, the capture continues only according to the configured failure policy
until the requested device span has been covered or capture is terminated.
Observed sample count, device-span count, and missing sample count remain
separate quantities.

## Workstream E: immutable gap map and masked dense reader

Observed IQ chunks remain byte-for-byte evidence.  A gap map derived from the
validated timeline records each discontinuity:

```text
segment_index
stored_sample_offset
device_sample_offset
missing_sample_count
expected_counter
actual_counter
reason
metadata/header evidence digest
```

The map is immutable and content-addressed.  Standard input binding includes
its digest so analysis deduplication changes when continuity evidence changes.

A V2 reader exposes both observed and dense operations:

- `iter_observed_spans()` yields only recorded samples and their device
  coordinates.
- `read_device_span(start, count)` returns samples, a boolean validity mask,
  and continuity-segment IDs.  Missing locations are logical CI16 zeros with
  `valid=false`.

Logical filling is the default because it avoids rewriting or expanding raw
evidence.  A materialized zero-filled artifact may be generated for a legacy
consumer, but it must include the identical gap map and mask digest.

Legacy recordings whose counters are absent remain `continuity=unknown`; the
system must not guess how many zeros to insert from host timing.

## Workstream F: gap-aware analysis and presentation

- Waterfalls and power plots render invalid spans as blank/hatched regions,
  not ordinary zero-power signal.
- Probe, FFT, GLRT, pilot, and frame windows crossing an invalid span are
  rejected with an explicit reason.
- Trajectory association and replay split at gaps.
- Frame timing, modulo-pi phase, carrier bias, CFO, Doppler rate, and Kalman
  filters begin a new episode after every gap.
- Long/global fits may use multiple segments only with independent per-segment
  nuisance intercepts and real device time.  They may not bridge phase.
- Scanner frames are independent across retunes and display their own metadata
  integrity status.
- The web UI and Standard/scanner summaries expose gap count, missing duration,
  continuity observability, buffer count/readback, and queue high-water mark.

## Implementation sequence and checkpoints

### C0: contracts and golden behavior

- Add V2 capture/scanner contracts and the shared validator.
- Freeze golden fixtures for contiguous, exact-gap, overflow-only, reset, and
  malformed metadata cases.
- Checkpoint: no V1 serialization or digest changes.

### C1: upstream metadata vertical

- Implement the metadata receive API in `pluto-plus-utils`.
- Pin the reviewed upstream commit and compatible libiio build in Leo.
- Checkpoint: adapter refuses a missing capability/header/counter and maps one
  valid block exactly.

### C2: dwell reset, queue, and storage validation

- Add K=8 reset/readback at capture start.
- Add the bounded producer/consumer path.
- Rerun continuity validation in storage.
- Checkpoint: fake injected storage stalls never block the producer; queue
  exhaustion fails explicitly.

### C3: scanner target isolation

- Add per-target destroy/tune/settle/K/readback/create ordering.
- Persist per-frame metadata in scanner manifest V2.
- Checkpoint: fake queued samples from a prior tuning cannot enter the next
  frame.

### C4: gap map and analysis

- Publish the gap map and masked dense reader.
- Make Standard/scanner window scheduling and stateful estimators gap-aware.
- Checkpoint: no accepted analysis window or state transition crosses an
  invalid sample.

### C5: bounded hardware red/green

User authorization covers radios `192.168.1.20` and `192.168.1.21`.  All new RF
tests remain bounded to at most 30 minutes and respect production radio leases.

1. Pause and drain scheduled acquisition; verify exclusive leases.
2. Attest serial, firmware metadata ABI, sample rate, refill size, K readback,
   and TX-muted state.
3. Reproduce a short K=1 red control: a counter gap or explicit failure is
   required; a normal continuous result is a test failure.
4. Run K=8 on each radio with the production dwell refill size.
5. Inject bounded consumer stalls that cover compression and shard finalization.
6. Run one paired-radio dwell canary and one scanner burst.
7. Restore TX-muted state and previous capture-control state.

Hardware acceptance:

- every returned block has a valid counter and stream identity;
- K readback equals eight;
- no counter gap in green arms;
- no counter regression, duplicate, or sequence disagreement;
- producer queue never overflows and high-water remains below 75%;
- scanner target metadata begins after its tune/reset boundary;
- any deliberate red event is logged, persisted, shown, and rejected by
  stateful analysis.

### C6: deployment and observation

- Deploy behind a continuity-capture release/config digest.
- Canary one radio, then both dwell radios, then scanner.
- Reprocess only newly captured V2 bundles; legacy evidence remains unchanged.
- Observe at least one complete scheduled dwell/scanner cycle and verify web UI
  products, manifests, logs, metrics, and queue telemetry.
- Publish an implementation/timing report and make `origin/main` match the
  verified deployment commit.

## Test matrix

| layer | required tests |
|---|---|
| validator | gap of 1, N, and multiple N; duplicate; regression; wrap; reset; flag-only overflow; sequence disagreement |
| upstream port | IQ/header atomicity; invalid capability; invalid counter flag; reset lifecycle; K readback |
| adapter | exact contract mapping; timing method; fail-closed admission; independent validation |
| queue | fast/slow consumer; injected compression/fsync delay; queue full; cancellation; two radios |
| storage | segment/chunk cut; exact missing total; validated-chain summary; corruption caught independently |
| dense reader | logical zeros; validity mask; segment IDs; slicing across multiple gaps; large sparse gap |
| analysis | crossing windows rejected; Kalman/phase reset; no global phase bridge; blank presentation region |
| scanner | per-target call order; no stale tuning; V2 manifest reopen; metadata unavailable failure |
| hardware | K=1 red; K=8 green; both radios; paired dwell; scanner; bounded stall injection |

## Deployment gates and rollback

Do not deploy unless:

- all component-owned and relevant integration tests pass;
- all V1 golden contracts remain unchanged;
- both radios attest the required metadata ABI;
- K=8 reset/readback works on `.20` and `.21`;
- the bounded K=8 hardware canary has zero gaps;
- Standard/scanner stateful analysis demonstrates gap resets on injected
  fixtures;
- capture-control and radio leases can be restored exactly.

Rollback triggers include any metadata/IQ association doubt, counter
regression, scanner stale-tuning evidence, queue overflow, unexplained runtime
increase, contract incompatibility, or missing UI integrity warning.

Rollback restores the prior service release and capture configuration but does
not silently restore continuity-unobservable production capture.  If the
metadata path is unavailable, live capture remains paused or explicitly
degraded until an operator chooses a documented legacy mode.  Already sealed
V2 bundles and their gap evidence remain immutable.

## Completion evidence

The implementation report must include:

- exact source and deployed commits for Leo, `pluto-plus-utils`, libiio, and
  firmware;
- contract and configuration digests;
- unit/integration/hardware test commands and results;
- K readback, counter-gap, queue, and runtime distributions by radio/mode;
- example contiguous and deliberately gapped manifests/readers/plots;
- one dwell and scanner UI link;
- deployment and rollback verification;
- remaining limitations, particularly the lack of an independent UTC sample
  clock and the distinction between zero-filled coordinates and observed IQ.
