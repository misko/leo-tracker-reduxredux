# Ring-free 2.5 + 25 MS/s frame-coverage plan

## Outcome

Make the existing two-radio production capture complete every requested payload
frame for a simultaneous dual-RX 2.5 MS/s leg and single-RX 25 MS/s leg, while
keeping counter gaps informational.

For a successful capture:

- low leg recording coverage is 100% of its requested device window on RX0 and
  RX1;
- high leg delivery coverage is exactly 100% of its requested finite frames;
- in-segment and inter-segment gaps are measured and persisted, but do not
  reject the capture;
- direct-async RAM-ring extension is false and every DDR/RAM-ring requested,
  admitted, capacity, and capture value is zero; and
- IQ is committed through the existing local-filesystem raw stage and
  device-axis publisher, never through an accumulating device RAM ring and
  never beneath `/mnt/qnap01`.

This is a focused correction to the existing V3 2.5 + 25 MS/s path. It does not
need a new scheduling, capture-plan, recording-manifest, or analyzer contract.
When gaps occur, the existing recording contract truthfully publishes the pair
as `DEGRADED` with partial observation integrity, even though transport delivery
completed successfully. `COMMITTED` remains reserved for lossless observation.

## Evidence and diagnosis

The current `pluto-plus-utils` ladder at `7578cab` completed both bounded
ring-free 25 MS/s cells on radio `19f2/RX0`:

| Nominal duration | Requested frames | Returned frames | Delivery coverage | Segments |
| ---: | ---: | ---: | ---: | ---: |
| 3 seconds | 72 | 72 | 100% | 2 |
| 20 seconds | 477 | 477 | 100% | 8 |

The cells had counter gaps, as expected at the measured transport rate, but no
requested frame was lost. The ladder used v0.46 final firmware, ABI 3,
1,048,576 samples per frame, 15 kernel buffers, 64-frame finite segments,
tandem HOLD, and zero RAM-ring slots.

The deployed Leo release pins `pluto-plus-utils` at `fd76f66`. Current upstream
contains the direct-async CMA priming fix in `605384f`: prime the ordinary scan
layout with two kernel buffers, release it, then restore the requested 15-buffer
direct queue. The old runtime primes with all 15 buffers and immediately opens
another 15-buffer queue, transiently requiring roughly twice the contiguous DMA
allocation. Leo's failed pair stopped after six or seven high-rate frames with
`ENODATA`; the current ladder completed every frame on the same radios.

The first staged Leo high-leg gate exposed a second, independent integration
defect after returning its first complete 64-frame segment. Leo normalized all
direct-async segments into one logical metadata generation, but required the
device counter at the next segment to remain aligned to a whole 1,048,576-sample
frame. A fenced direct-async re-arm can resume after an arbitrary number of
device samples. Preserve that exact counter gap, advance the normalized source
sequence by one returned block when the gap is not a whole-refill inventory,
and allow the device-axis writer to zero-fill the exact gap. The ordinary
continuous-IIO validator must retain its stricter whole-refill rule.

The bounded paired tandem-AUTO gate then failed closed after 42 of 72 requested
high-rate frames with `ENODATA`; its low peer was quarantined and no manifest
published. The successful HOLD gates completed 3 seconds, 20 seconds, and the
20-second radio-role swap at 100% delivery. Production therefore uses the
additive `production-direct-async-2p5-10-15-25-hold-6-v1` scheduler selector.
It emits the existing immutable V3 intent with explicit HOLD assignments and a
`gain_rollout:tandem_hold_v1` evidence tag. It does not reinterpret old V3
intents or remove AUTO from their contract.

The first deployed 60-second HOLD canary then found the next measured limit.
The ordinary dual-RX 2.5 MS/s leg compressed shards during RF and filled its
bounded host queue after 117,440,512 of 150,000,000 requested device samples
(78.294% delivery). Peer cancellation stopped the high leg after 555 of 1,431
frames (38.784% delivery), so the session correctly remained an unpublished
partial spool. This is a storage-service-time failure, not a radio-ring or
direct-async failure: the low leg had already written seven compressed shards
while RF was active.

## Preserve the contracts that already fit

Keep these existing contracts and semantics unchanged:

- `DirectAsyncRequestV1`: 1,048,576 samples per frame, at most 64 frames per
  segment, one receiver, and a ceiling-derived finite frame target;
- `DirectAsyncEvidenceV1`: exact returned-frame closure, distinct upstream
  generations per segment, counter-derived missing samples, inter-segment
  skips, and stored/drained sample closure;
- `CapturePlanV5` and `RecordingManifestV6`; and
- device-axis zero-fill publication and Standard-native analysis.

The direct-async evidence model already makes a finalized high-rate raw stage
equivalent to 100% delivered-frame coverage. A transport-incomplete run retains
failure evidence and must not publish a manifest. The coordinator does need to
stop treating a counter-gapped but logically closed device-axis receipt as a
peer transport failure. Do not weaken frame closure and do not reinterpret old
V3 intents or V6 manifests.

## Implementation slices

### 1. Pin the runtime that passed

Pin the Leo hardware dependency and lockfile to exact
`pluto-plus-utils@7578cab938a0658492f4350abbd350fbef62fb30`, which contains the
CMA priming fix and is the revision used for the successful 3-second and
20-second cells.

Update the dependency provenance document, release-local metadata-runtime
receipt expectations, staging tests, and production-cutover verifier. The
staged release must prove all of the following before it can own a radio:

- exact PPU source commit `7578cab`;
- matched host libiio/pylibiio metadata ABI 3;
- firmware `v0.46-plutoplus-spf-iq-direct-async-ring-v1`;
- advertised direct-async support; and
- ring extension disabled with zero DDR/RAM-ring admission.

No fallback to the old PPU revision, ordinary unobservable IIO, DDR ring, or a
runtime source checkout is permitted.

### 2. Match the successful arm sequence

Add RX0 and RX1 revisions of the 25 MS/s production profile rather than editing
the published `direct-async-v7` documents. The new revisions retain the exact
rate, bandwidth, frame size, 15-buffer direct queue, 64-frame segmentation,
storage policy, and receiver geometry, but set the coordinator's external
`prime_refills` to zero. PPU's corrected metadata session performs the one
required two-buffer scan-layout prime internally before restoring 15 buffers.

Point newly compiled production authority at the new profile revisions while
retaining the v7 profiles for old persisted intents and recordings. Verify the
exact selected profile name and digest at intent compilation and execution. Add
the two new exact name/digest pairs to Standard-native's reviewed direct-async
profile identity table without removing the v7 identities.

Use tandem HOLD for the first paired qualification because it is the geometry
already proven by the ladder. Separately run the same bounded single-radio and
paired gates with tandem AUTO before allowing the existing randomized V3
scheduler to resume. If AUTO does not achieve 100% delivery, do not silently
change V3 scheduling semantics; introduce an additive HOLD-only policy in a
separate reviewed change.

### 3. Separate delivery closure from observation integrity

The current coordinator correctly produces a `RecordingStreamV3` partial stream
when its device-axis writer inserts zero fill, but then the pair-level
`fail_session` check rejects every partial stream before publication. Refine the
internal outcome model so it distinguishes:

- **transport complete:** the requested logical device span is sealed, storage
  has no enqueue/write failure, and the high leg has exact
  `DirectAsyncEvidenceV1` frame closure;
- **observation degraded:** the sealed span contains counter-proven zero fill or
  an overflow; and
- **transport failed:** a target frame, peer, queue entry, writer receipt, or
  logical endpoint is missing.

`FAIL_SESSION` must still reject the entire pair when either peer is transport
failed. It should not reject a pair merely because one or both fully sealed
streams are observation-degraded. Publish that pair as `RecordingManifestV6`
state `DEGRADED`, with each gapped `RecordingStreamV3` remaining `PARTIAL` and
carrying its existing explicit integrity explanation. This uses behavior already
allowed by the immutable stream and manifest contracts.

Add no success path for a shortened high-rate frame inventory. The direct raw
stage may finalize only after `returned_frames == target_frames`; otherwise the
whole pair remains quarantined without a manifest.

### 4. Keep the RF read path non-blocking

Retain the existing producer/consumer ownership split for both device-axis
legs:

1. the radio thread reads and validates one direct-async frame;
2. it hands the frame once to the bounded host queue without waiting for
   compression;
3. each storage thread appends CI16 to its own bounded filesystem-backed raw
   stage; and
4. after both radio read loops close, each publisher constructs its device-axis
   stream, zero-fills counter gaps, compresses it, and atomically publishes the
   bundle.

The 60-second failure makes this staging mandatory for the ordinary dual-RX
2.5 MS/s leg as well as the finite direct-async leg. Its bound is exactly the
admitted logical payload size, 1.2 GB at 60 seconds. Give post-RF replay the
existing raw-stage finalization timeout; do not make compression part of the
bounded RF service interval. Preserve queue-full fail-closed behavior if even
the sequential raw-stage append cannot keep pace. Storage admission reserves
both the raw stage and a full-size final output for every device-axis leg. A
session drain barrier prevents the faster low leg from starting compression or
raw-stage `fsync` while the slower finite-frame high leg is still reading RF.

The bounded kernel queue and host handoff queue are transport backpressure, not
capture rings. Do not add PPU RAM-ring slots, a user-space circular IQ store, or
an unbounded queue. Keep queue-full fail-closed: it is better to retain a partial
spool and exact failure evidence than claim 100% coverage after dropping a
frame.

First test the paired path with only the PPU pin and corrected arm sequence. Do
not pre-emptively redesign conversion or storage. If it still fails, measure
these stages in order and change only the first stage that fails its budget:

1. PPU frame drain alone;
2. Leo adapter validation and complex-to-CI16 conversion;
3. high-leg raw-stage append;
4. concurrent dual-RX 2.5 MS/s drain; and
5. final compression/publication after RF has closed.

Any hot-path optimization must preserve the existing domain IQ and storage
ports and include component-owned tests.

### 5. Make coverage explicit

Add a pure coverage projection over capture and failure evidence. Report, per
radio stream:

- `delivery_coverage_pct`: returned high-rate frames divided by requested
  frames, or sealed low-rate logical device samples divided by requested
  samples;
- `observed_density_pct`: physically observed samples divided by the sealed
  logical device span for either recording stream;
- `in_segment_density_pct`: returned high-rate samples divided by returned
  samples plus counter loss excluding inter-segment rearm skips; and
- `transport_density_pct`: returned high-rate samples divided by returned
  samples plus all counter-derived missing samples.

Only delivery coverage is the publication gate and it must equal 100% for both
peers. Density is scientific/transport context, not a success threshold. Derive
percentages from integer counters at presentation time; do not persist rounded
floats or alter the immutable manifest. Label a 100%-delivered, gapped capture
as operationally successful and scientifically `DEGRADED`, never lossless.

Expose the projection in the capture result, operator CLI, and API/repository
view used to inspect recordings. Failed partial spools should show their exact
delivery percentage from `capture-failure-stream-*.json` without being mistaken
for recordings.

## Exact 60-second geometry

The production dwell remains 60 seconds:

| Leg | Requested samples | RX paths | Finite frames | Segments | Published CI16 maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2.5 MS/s | 150,000,000 per RX | RX0 + RX1 | ordinary bounded refills | n/a | 1.2 GB |
| 25 MS/s | 1,500,000,000 | RX0 or RX1 | 1,431 | 23 | 6.0 GB |

The high leg drains 1,500,512,256 delivered samples because the finite target
rounds up to a whole frame. Only samples intersecting the requested device
window are published; the 512,256-sample ceiling tail and any later frames
shifted beyond the window by gaps are accounted as deliberately drained. A
successful pair publishes at most 7.2 GB of uncompressed CI16 before
compression.

## Verification

### Component tests

- Dependency tests pin the exact PPU commit in `pyproject.toml`, `uv.lock`, the
  runtime receipt, staged release, and cutover verifier.
- Profile tests prove the new 25 MS/s revisions have zero external primes,
  direct-async tags, one RX, 15 kernel buffers, 64-frame segments, and no ring
  policy.
- Adapter tests prove direct-async readback, ring extension false, and every
  DDR/RAM-ring field zero.
- Coordinator tests inject in-segment and inter-segment gaps while returning all
  target frames; the bundle must publish `DEGRADED` with 100% delivery coverage
  and truthful densities.
- A direct-async segment-rearm test uses a non-refill-aligned counter gap; it
  must retain all finite frames, persist the exact inter-segment skip, and leave
  the default continuous-IIO whole-refill validator strict.
- Peer-policy tests prove `FAIL_SESSION` still quarantines a missing/short peer,
  while allowing two transport-complete device-axis receipts to publish when
  their only defect is counter-proven observation loss.
- Failure tests stop at frames 0, 6, 7, 63, 64, and the final frame; no manifest
  may publish, and failure coverage must be exact.
- Storage tests cover queue-full, writer failure, cancellation, peer failure,
  final-frame truncation, partial-spool retention, and atomic publication.
- Compatibility tests continue parsing old profiles, V3 intents, V5 plans, V6
  manifests, and their existing evidence unchanged.

### Bounded hardware gates

Run no RF as part of implementation or ordinary CI. With fresh explicit user
authorization and capture paused/drained, advance through these short gates:

1. retain the completed latest-PPU single-radio HOLD evidence at 3 and 20
   seconds;
2. repeat 3 and 20 seconds through the Leo high-leg adapter and raw stage;
3. run paired 2.5 + 25 MS/s for 3 seconds, then 20 seconds, with one radio as
   the high leg;
4. repeat the 20-second pair with radio roles swapped;
5. qualify tandem AUTO with the same bounded sequence; and
6. only after all short gates pass, authorize one 60-second production canary.

For each paired gate require:

- 100% delivery coverage on the 25 MS/s stream;
- 100% sealed logical device-window coverage on both 2.5 MS/s receiver
  recordings, with observed density reported separately;
- exact segment/generation inventory and counter arithmetic;
- gaps accepted and visible in both density metrics;
- zero device RAM-ring admission and no queue enqueue failures;
- no `ENODATA`, short refill, peer-only publication, or unexplained truncation;
- exact original RX setting restoration; and
- for the 60-second canary, a committed V6 bundle that completes one
  Standard-native reprocess and appears correctly in the API/UI.

All proposed RF time totals less than three minutes and remains far below the
repository's 30-minute ceiling. Stop at the first failed gate and retain its
partial evidence; do not turn the ladder into a long-running campaign.

## Cutover and rollback

Stage and verify the release while normal capture remains paused. Cut over only
with both radio locks drained and no active acquisition lease. Resume the V3
supervisor only after the 60-second canary and processing vertical pass.

Rollback restores the previous release and dependency together under the same
pause/drain fence. New profile revisions are additive, so old releases continue
to read prior recordings; do not resume an old release while an operation
referencing a new profile revision is queued.

## Completion criteria

The change is complete when a production 2.5 + 25 MS/s pair returns all 1,431
high-rate frames, seals the full 150,000,000-sample low-rate device window on
both receivers, persists truthful observed/zero-fill density evidence with zero
RAM-ring admission, atomically publishes its V6 recording (`DEGRADED` when
gapped), completes Standard-native processing, and remains inspectable as 100%
delivery coverage through the CLI and API.
