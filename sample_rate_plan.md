# Native 2.5, 3, and 5 MS/s capture and Standard-analysis plan

Date: 2026-08-26
Status: approved for implementation, test, deployment, and bounded verification
Branch: `codex/3m-5m-sample-modes`
Base: `origin/main` at `fce4d6c1d4cfb3a485e682577c5e938df486afbf`

## Decision

Leo will use one native-rate Standard pipeline for 2.5, 3, and 5 MS/s. It will
not resample these recordings for Standard analysis.

Every finalized new-format recording will cover the complete requested FPGA
device-time interval. Counter-proven missing samples will be persisted as
literal CI16 zeros. The recording will also preserve mandatory validity
evidence that distinguishes observed samples from synthetic zeros.

A gapped recording is therefore:

- storage-complete over its proven device-time interval;
- observation-partial because some IQ was not measured; and
- scientifically eligible only through validity-aware analysis.

Zero fill is a storage and coordinate representation. It is never evidence that
the receiver measured zero-valued IQ.

This plan supersedes the resampling alternatives in
`docs/architecture/3m-5m-sample-rate-modes-plan.md`. That document remains the
historical capture-mode and qualification record; its published-contract and
hardware-evidence boundaries remain authoritative.

## Invariants

1. Published V1 and V2 contracts, bundles, digests, and 2.5 MS/s goldens remain
   immutable.
2. A new independent recording-contract major represents physical device-axis
   zero fill. Existing V2 semantics are not reinterpreted.
3. A finalized recording has an exact requested device endpoint. An unknown
   tail, absent counter authority, early cancellation, or terminal writer
   failure is quarantined rather than fabricated.
4. Every scientific result binds the source manifest, timeline, gap map,
   validity inventory, sample rate, and exact algorithm/configuration identity.
5. Standard analysis never treats synthetic zeros as observed samples.
6. All time-domain geometry derives from the native sample rate. No resampler
   appears in the capture or Standard-analysis graph.
7. Stateful sample/phase estimators never carry unreviewed state across a
   continuity boundary.
8. A complete computation over partial observations reports
   `PARTIAL_COVERAGE`, not capture continuity and not an analysis failure.
9. The existing frozen Standard pipeline remains available for rollback.

## Target geometry

Paired CI16 receive data contains I16 and Q16 for each of two receivers, or
eight bytes per sample instant per radio.

| Rate | 60-second samples/radio | Raw bytes/radio | Two-radio raw bytes |
|---:|---:|---:|---:|
| 2.5 MS/s | 150,000,000 | 1.20 GB | 2.40 GB |
| 3 MS/s | 180,000,000 | 1.44 GB | 2.88 GB |
| 5 MS/s | 300,000,000 | 2.40 GB | 4.80 GB |

These are exact logical/decompressed sizes. Compressed `.zst` bytes vary with
RF content and zero-run length and are not required to match.

The initial profiles retain the reviewed 2.5 MHz analog bandwidth. Higher
sample rate means greater oversampling, not wider qualified RF bandwidth.

## Architecture

```text
FPGA blocks + counters
          |
          v
Recording V3 writer
  observed chunks + physical zero-fill chunks
          |
          +-- fixed-length device-axis IQ
          +-- timeline + gap map + validity inventory
                              |
                              v
                    Validity-aware IQ port
             +----------------+----------------+
             |                |                |
             v                v                v
       additive metrics  complete windows  segment-local state
       quality / power    FFT / GLRT / QAM  trajectory / Kalman
```

Historical V2 recordings enter the same analysis port by synthesizing the
device-axis zeros from their verified observed IQ and gap map. New V3
recordings read their physically persisted zeros. Downstream analyzers do not
branch on the storage version.

## 1. Additive recording contracts

Introduce independent contracts rather than subclassing V2 and changing its
meaning:

- `RecordingManifestV3`;
- `RecordingStreamV3`;
- `DeviceAxisRecordingChunkV1`;
- `DeviceAxisContentKind = observed | zero_fill`;
- `ValidityInventoryV1`; and
- a new explicit storage-layout identity such as
  `zstd-128m-device-axis-zero-v1`.

Each V3 stream records:

- `requested_sample_count` and `logical_sample_count`;
- `observed_sample_count` and `zero_fill_sample_count`;
- applied rate, bandwidth, tuning, receiver inventory, and timing;
- ordered device-axis chunks with content kind;
- compressed and uncompressed sizes and digests;
- an observed-IQ digest and a logical device-axis digest;
- the original refill timeline and its digest;
- the counter-derived gap map and its digest; and
- a validity-inventory digest.

The validators require:

```text
logical_sample_count == requested_sample_count
logical_sample_count == observed_sample_count + zero_fill_sample_count
sum(chunk.sample_count) == logical_sample_count
logical_uncompressed_bytes == logical_sample_count * receiver_count * 4
chunks cover [0, logical_sample_count) exactly once
zero_fill chunk intervals == gap-map missing intervals
observed chunk intervals == validity observed intervals
```

Every zero-fill chunk must decompress to literal CI16 zeros. A nonzero value in
a zero-fill chunk, a gap-map disagreement, overlap, hole, digest mismatch, or
coordinate regression fails verification.

## 2. Capture and storage behavior

The first authoritative sample counter anchors device sample zero. The target
exclusive counter is `first_counter + requested_sample_count`.

For each received block, the storage consumer:

1. verifies its metadata and counter sequence;
2. computes any exact missing interval before the block;
3. streams bounded reusable CI16-zero buffers through the compressor;
4. writes the observed IQ block;
5. advances the device-axis writer cursor; and
6. updates observed, zero-fill, logical, timeline, gap, and digest evidence.

Zero generation and compression never run on the RF refill thread. The writer
must not allocate a complete gap-sized array.

The writer may seal only after counter evidence proves the requested exclusive
endpoint. An internal or proven terminal gap can be zero-filled. A missing
counter, early stop, cancellation, queue/consumer failure that prevents endpoint
proof, or unknown tail produces quarantined partial evidence and no V3 manifest.

A sealed gapped stream retains partial/degraded observation integrity even
though its physical IQ layout is complete. Storage completeness must not be
confused with RF continuity.

## 3. Shared validity-aware IQ port

Add a narrow analysis port that exposes:

- native `sample_rate_hz` and full logical `sample_count`;
- observed and missing counts;
- ordered valid and missing device-time intervals;
- continuity segment IDs;
- bounded reads returning IQ plus validity;
- iteration over valid blocks only;
- segment-local contiguous readers; and
- global-window classification.

The canonical validity representation is a compact ordered run list derived
from the gap map, not a permanently allocated dense boolean array. Bounded
reads may materialize a temporary mask for their block.

The window classifier returns one of:

- `valid`;
- `gap_overlap`;
- `continuity_boundary`; or
- `outside_span`.

It verifies the digest-bound gap map and timeline before returning any science
input. V2 synthesized zeros and V3 physical zeros must yield identical logical
IQ, validity runs, segment coordinates, and global time mapping.

## 4. Native-rate Standard input and topology

Add `StandardPathInputBindV4` and one separately versioned
`standard-native-v1` definition. The existing Standard compiler and its
`CAPTURE_ONLY` rejection remain frozen.

V4 binds:

- logical, observed, and missing sample counts;
- native sample rate and requested duration;
- observed-IQ, logical-IQ, timeline, gap-map, and validity digests;
- ordered continuity-segment inventory;
- first/last counter and UTC timing evidence;
- exact radio, receiver, tuning, bandwidth, and profile identity; and
- native-rate science configuration and implementation digests.

The topology remains:

```text
four receiver-path jobs
  -> two radio reducers
  -> paired reducer
  -> presentation
```

The existing Research rate-baseline lane remains an evidence oracle. Its
`evidence_only` authority is not reinterpreted as Standard authority.

## 5. Standard stage behavior

### Input binding and probe schedule

Build the schedule across the complete requested device-time span. Every
scheduled opportunity is retained and classified as valid or gap-excluded.
An excluded opportunity is not a signal-absent result.

### Quality

Compute extrema, clipping, energy, and counts over valid samples only. Publish
logical, observed, and missing counts plus uncovered-region count. Synthetic
zeros cannot reduce clipping rate or mean amplitude.

### Power timeline

Keep bins on the global device-time axis. Accumulate valid energy and valid
sample count in each bin. An empty bin is unavailable; it is not zero power.

### Numerical waterfall

Transform only FFT windows whose complete support is valid. Reset carry at
each continuity boundary. Preserve global time bins and publish valid-transform
counts and missing coverage; presentation renders unavailable cells distinctly
from measured low power.

### Pilot acquisition and frame extraction

Run the existing numerical kernels only on wholly valid probes, symbols, and
frames. Gap-overlapping opportunities receive an explicit exclusion reason.
Candidate times are mapped back to global device sample and UTC coordinates.

### QAM and EVM

Demodulate complete valid frames only. Aggregate error energy, reference
energy, and symbol counts. Never treat zero fill as a constellation point and
never average per-segment EVM percentages directly.

### Full-capture GLRT

Keep the global 20 ms window / 10 ms stride schedule. Reject any window whose
support intersects a gap. Fit lines and candidate basins independently within
each continuity segment.

### Local CFO

A CFO estimate is eligible only when its complete supporting samples lie in
one segment. It retains absolute device time and segment identity.

### Trajectory, Hough, replay, and de-aliasing

Attach segment identity to every detection and observation. Fit Hough lines,
trajectory feedback, conditioned replay, alias selection, robust refinement,
and final trajectory arcs independently per segment. Do not infer phase or
signal support through missing IQ. A later noncoherent association may relate
arcs while preserving their independent provenance.

### Kalman tracking

The first release resets and reseeds a filter in every segment. A future
separately reviewed algorithm may perform prediction-only propagation through
a gap with explicit covariance growth; the initial Standard-native contract
does not claim this.

### Pilot Doppler

Use complete valid frames and windows only. Rate, phase, and bias fits remain
segment-local. A gap longer than the algorithm's supported within-segment frame
gap always splits the result.

### Path report

Report separately:

- logical and observed sample coverage;
- scheduled, valid, analyzed, and gap-excluded windows;
- valid segment inventory;
- processing completion; and
- scientific disposition.

A successfully processed gapped path returns `PARTIAL_COVERAGE`. Candidate,
no-candidate, and insufficient-evidence dispositions remain separate.

### Alternate tracks

Run alternate Hough/line finding per segment using segment-tagged persisted
pilot observations.

### Radio reducer

Both receiver paths from one dual-RX stream bind the same validity inventory.
Merge sufficient statistics and retain segment-local track inventories.

### Paired reducer

Map both radios to a common UTC axis and intersect their valid intervals for
paired claims. Segment ordinals are not assumed to match. No cross-gap or
cross-radio phase coherence is claimed.

### Presentation

Keep the complete requested time axis. Mark gaps as unavailable rather than
displaying zero fill as dark measured RF. Display logical, observed, eligible,
and analyzed coverage.

## 6. Native-rate geometry

All time-defined geometry converts to samples using the input rate. Frequency
searches remain expressed in hertz. Amplitude thresholds remain in CI16/dBFS.

Every existing 2.5 MS/s literal is classified before promotion:

- a frozen legacy/product constant remains untouched;
- a physical-time constant is derived from `sample_rate_hz`;
- a rate-dependent spectral/template identity receives a reviewed per-rate
  configuration and digest; or
- a genuinely 2.5-only scientific contract remains unavailable at 3/5 MS/s.

Known review points include dwell Doppler, frame period/sample geometry,
trusted acceptance, CFO alias spacing, pilot template identities, waterfall
FFT geometry, calibration, and qualification oracles.

## 7. Product and reducer rules

Add new major versions only where source or gap semantics change. Do not mutate
published Standard products.

Reducers combine sufficient statistics:

- power: energy sum and valid sample count;
- quality: clipping count, valid count, and extrema;
- waterfall: spectral sums and valid transform counts;
- QAM: squared-error, reference-energy, and symbol counts;
- pilot/GLRT: scheduled, eligible, analyzed, and passing opportunity counts.

Do not average dB values, trajectory slopes/intercepts, Kalman states, or EVM
percentages. Trajectories and filter states remain segment-local products.

## 8. Component and property tests

### Contract and storage

- V1/V2 JSON, parsing, digests, readers, and golden fixtures remain unchanged.
- V3 round trips at 2.5, 3, and 5 MS/s.
- No gap, one-sample, initial, internal, multiple, refill-sized, chunk-boundary,
  overflow-only, and proven terminal gaps.
- Genuine observed all-zero IQ remains valid.
- Zero-fill bytes are exactly zero at exact device offsets.
- Gap map, timeline, chunk inventory, counts, sizes, and digests close exactly.
- Tampered zero fill, mask, gap map, timeline, or device coordinate fails.
- Unknown endpoint, cancellation, queue failure, or writer failure refuses V3
  publication and preserves quarantined evidence.
- Results are invariant to refill and storage chunk partitioning.

### Validity and coordinate properties

- Randomized gap maps preserve the exact stored/device/segment bijection.
- V2 synthesized and V3 persisted device-axis reads agree bit for bit.
- Bounded reads and iteration never lose validity or segment identity.
- Global sample, counter, seconds, and UTC mappings are monotonic and exact.
- Empty terminal segments and zero-length continuity boundaries remain visible
  to state-reset logic but are not analyzed.

### Analysis behavior

- Invalid zeros cannot affect quality, power, clipping, or QAM statistics.
- Every FFT/probe/symbol/frame/GLRT window overlapping a one-sample through
  refill-sized gap is excluded exactly once.
- Deterministic signals on opposite sides of a gap never share an FFT carry,
  phase fit, trajectory, replay, Doppler segment, or Kalman state.
- Scheduled opportunities partition exactly into valid, gap-excluded, and
  outside-span inventories.
- Weighted reducers are invariant to segment/chunk ordering and partitioning.
- Paired validity intersections close for differing radio gaps and start times.

### Native-rate scientific equivalence

Generate equivalent physical fixtures directly at 2.5, 3, and 5 MS/s. No
resampler appears in the analysis graph. Under predeclared tolerances compare:

- event and pilot epoch in seconds;
- power and clipping;
- CFO and Doppler in hertz;
- trajectory slope/curvature in physical units;
- phase on valid arcs; and
- QAM/EVM.

Existing 2.5 MS/s golden products change only through separate explicit review.

## 9. Real-corpus and performance qualification

Use existing recordings before collecting new RF:

- one contiguous 2.5 MS/s production dwell;
- 3 MS/s lossless `cap-20260825T213600-dd352bd0e4fc`;
- 5 MS/s full-span gapped `cap-20260825T214800-edc045ea9a07`; and
- truncated 5 MS/s `cap-20260825T211500-642ccf40a8c1` as a negative case.

The reviewed 5 MS/s oracle has 300,000,000 logical samples, 284,795,648
observed samples, 15,204,352 missing samples, 58 gaps of 262,144 samples, and
59 valid segments per radio. The integration test must close this exact
inventory, prove deterministic reruns, and prove that paired analysis uses the
two-radio valid-time intersection.

Performance gates:

- two-radio 5 MS/s writer throughput at least 100 MB/s;
- zero enqueue failures and terminal rejected refills;
- userspace queue high-water no greater than 24/32;
- no zero generation or compression on the RF refill thread;
- no live writer after capture return and no `.partial` residue;
- no OOM, swap activity, storage error, or RAID degradation; and
- initial Standard-native heavy concurrency two, raised to four only after
  measured memory and I/O headroom.

## 10. Delivery sequence

1. Land contracts and the dual-format validity-aware reader dark, with no
   production behavior change.
2. Land V3 capture writing behind an exact profile/storage-layout feature gate.
3. Run component, property, compatibility, and performance tests.
4. Run Standard-native evidence-only against the preserved 2.5/3/5 corpus.
5. Deploy read support and the disabled V3 writer; validate release integrity.
6. Enable V3 for a bounded 2.5 MS/s parity capture and Standard run.
7. Run one bounded 3 MS/s capture followed by Standard-native analysis.
8. Run one bounded 5 MS/s capture followed by gap-aware Standard-native
   analysis.
9. Promote 3 MS/s after full-coverage native-rate scientific parity.
10. Promote 5 MS/s after fixed-size zero-fill closure, partial-coverage science,
    writer headroom, and operational health gates pass.
11. Enable the ordered 2.5/3/5 ordinary-dwell pool only after all prior gates.

Initial qualification runs one high-rate analysis at a time and does not
overlap capture with heavy analysis. New RF time remains bounded below 30
minutes and does not displace normal CLI/UI or re-analysis work.

## Rollback

- Keep the existing V2 writer, frozen Standard compiler, and 2.5 MS/s profile
  available behind explicit configuration.
- A rollback disables V3 capture and Standard-native admission; it never
  rewrites or deletes a V3 bundle.
- Upgraded readers continue to verify both old and new recordings.
- Any contract, continuity, queue, writer, scientific, release-integrity, or
  hardware gate failure stops promotion and preserves all evidence.

## Definition of done

- Every finalized V3 dwell decodes to the exact requested device-time length.
- Every missing device sample is a physical CI16 zero with matching validity
  and counter evidence.
- Historical V1/V2 recordings remain unchanged and readable.
- One Standard-native graph analyzes 2.5, 3, and 5 MS/s without resampling.
- Lossless inputs take the all-valid fast path.
- Gapped inputs complete with truthful partial coverage and no cross-gap
  scientific computation.
- All component, scientific, integration, performance, release, deployment,
  and bounded hardware gates pass on the exact pushed revision.
