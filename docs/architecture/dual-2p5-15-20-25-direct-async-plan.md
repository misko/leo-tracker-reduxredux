# Dual 2.5 + 15/20/25 MS/s capture plan

## Decision

Introduce an additive production policy for simultaneous two-radio Starlink
capture with this exact six-dwell bag:

| Dwells per cycle | Low-rate leg | High-rate leg | Receiver geometry |
| ---: | ---: | ---: | --- |
| 2 | 2.5 MS/s | 15 MS/s | low leg dual RX; high leg single RX |
| 2 | 2.5 MS/s | 20 MS/s | low leg dual RX; high leg single RX |
| 2 | 2.5 MS/s | 25 MS/s | low leg dual RX; high leg single RX |

Every pair observes one digest-stable randomly selected Starlink channel and
edge. The high-rate radio, high-rate receiver, and tandem HOLD/AUTO controller
remain digest-stable randomized choices. Each cycle is deterministically
permuted from a balanced two-of-each bag.

Use the qualified segmented direct-async path for all three high rates, with
ring extension explicitly disabled. The new policy must never allocate or
admit an in-device DDR/RAM ring and must never fall back to the old 20 MS/s
finite DDR-ring mode. The only transient buffering is the bounded DMA/kernel
buffer set and bounded producer/consumer queue needed to carry frames directly
to a filesystem-backed raw spool; neither is an accumulating capture ring.
One transport and one evidence model make admission, failure handling,
manifests, analysis, deployment, and rollback substantially easier to audit.

Suggested durable policy identity:

`production-direct-async-2p5-15-20-25-6-v4`

## Empirical prerequisite: current PPU DMA priming

The 2026-08-31 ring-free 25 MS/s canary establishes that the current
`pluto-plus-utils` direct-async ladder at `7578cab` returns every requested
frame on both production radios. Each independent three-second run returned
72/72 frames with original RX settings restored. Counter gaps were present and
are acceptable for this segment-aware policy; no DDR/RAM ring was requested or
admitted.

The deployed Leo release instead pins `pluto-plus-utils` at `fd76f66`, before
the direct-async CMA priming fix in `605384f`. The current implementation primes
the ordinary scan layout with two kernel buffers and then restores the requested
15-buffer direct queue. The older implementation primes with all 15 and
immediately reopens another 15-buffer queue, transiently requiring roughly
twice the contiguous DMA allocation while deferred kernel releases complete.

Treat a provenance bump containing `605384f` as a prerequisite, not an optional
optimization. Pin and verify the exact PPU commit in the staged release, retain
the qualified v0.46 final firmware requirement, and repeat the paired 2.5+25
canary before changing capture contracts. The native ladder result proves the
radios can complete a bounded 25 MS/s request; it does not by itself prove the
simultaneous low-rate peer plus raw-spool ingestion path.

## Why this is an additive generation

Current `main` already provides:

- V3 direct-async 2.5 + 10/15/25 MS/s production scheduling;
- direct-async 10, 15, and 25 MS/s single-RX profiles;
- V2 DDR-ring 2.5 + 20 MS/s scheduling and profiles; and
- Standard-native analysis for 2.5, 15, 20, and 25 MS/s.

The missing capability is a ring-free direct-async 20 MS/s production leg in
an exact 15/20/25 schedule. The V3 intent, V5 capture plan, and V6 recording
manifest are persisted public contracts whose literals close over 10/15/25.
They must remain byte-for-byte readable and semantically unchanged.

Add, rather than widen:

- `ProductionDwellClassV4`, `ScheduledRadioLegV4`, and
  `ProductionDwellIntentV4`;
- `CapturePlanV6`; and
- `RecordingManifestV7`.

Existing V1-V3 queued intents and V1-V6 recording manifests continue through
their current readers and execution paths.

## Fixed capture geometry

The low-rate profile remains
`starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4`: 2.5 MS/s, 2.5 MHz native
bandwidth, RX0+RX1, 60 seconds, device-axis storage, segment-aware continuity,
and fail-session peer semantics.

Add RX0 and RX1 variants of a 20 MS/s direct-async profile matching the
reviewed 15/25 MS/s family:

- 20 MS/s sample rate and 20 MHz RF bandwidth;
- one receiver and manual 30 dB seed gain;
- 60 seconds;
- 1,048,576 samples per direct-async frame;
- 64 frames per segment and 15 kernel buffers;
- filesystem-backed raw staging with device-axis zero-fill publication;
- `allow_segments`, `best_effort`, `fail_session`, and required device
  metadata; and
- the existing `DEVICE_BUFFER:DIRECT_ASYNC_SEGMENTED_V1` evidence policy.

At 20 MS/s, a 60-second leg requests 1,200,000,000 device samples, 1,145 DMA
frames, and 18 segments. Each segment is opened with direct-async ring
extension false and all DDR-ring requested/admitted/capacity counters at zero.
The final frame is drained only outside the requested device window; no extra
samples enter the recording.

The existing maximum-in-channel tuning rule remains authoritative. Both legs
bind the same channel and edge, but their IF centers differ as required to
maximize in-channel coverage at their native bandwidths.

## Storage and throughput envelope

CI16 uses four bytes per complex sample per receiver. Before compression, each
60-second pair has this envelope:

| Pair | Radio payload rate | Published IQ maximum | Admission before metadata |
| --- | ---: | ---: | ---: |
| 2.5 dual RX + 15 single RX | 80 MB/s | 4.8 GB | 8.4 GB + safety reserve |
| 2.5 dual RX + 20 single RX | 100 MB/s | 6.0 GB | 10.8 GB + safety reserve |
| 2.5 dual RX + 25 single RX | 120 MB/s | 7.2 GB | 13.2 GB + safety reserve |

Admission is intentionally larger than the published IQ maximum because the
high-rate direct-async leg also reserves an uncompressed raw staging file on
the recording filesystem. This is disk capacity, not a RAM ring. With the
current 8 GiB safety reserve, the approximate free-space gates are 15.8, 18.1,
and 20.3 GiB respectively, plus metadata. Keep the existing admission
calculation fail-closed and add exact regression assertions for all three
shapes.

## Implementation sequence

### 1. Add the immutable policy generation

Define the V4 schedule contract and digest function in
`leo.contracts.mixed_rate_schedule`. Close its allowed rates to 2.5, 15, 20,
and 25 MS/s and its dwell classes to exactly the three requested pairs.

Add a pure V4 schedule compiler in `leo.acquisition.mixed_rate_schedule`. Its
six-slot multiset is two of each class, permuted per cycle. Reuse the existing
unbiased, domain-separated selections for high radio, high RX, channel, edge,
and tandem controller, with a new V4 hash domain so the new policy cannot be
mistaken for V3.

### 2. Add 20 MS/s direct-async profile authority

Create the two reviewed 20 MS/s direct-async profile documents and admit 20
MS/s to the existing ring-free direct-async request resolver. Do not alter the
legacy 20 MS/s DDR-ring profiles or their digests, and do not make them a
fallback for the new policy.

Separate direct-async profile authority from V2 production profile authority.
The direct-async authority should expose the 2.5 MS/s dual-RX profile plus the
single-RX 10/15/20/25 profiles. V3 consumes its existing 10/15/25 subset; V4
consumes 15/20/25. This avoids silently changing a queued V2 20 MS/s intent
from DDR-ring to direct-async after deployment.

Fail configuration early if a direct-async policy is selected while the
feature gate is disabled, any exact profile revision is absent, a selected
profile carries a DDR-ring tag, or the adapter cannot attest ring extension
false and zero DDR-ring admission.

### 3. Carry the new intent through capture without reinterpretation

Add `CapturePlanV6` and a pure `compile_production_capture_plan_v6` compiler.
Reuse `ProductionRadioPlanV2` for each leg, but close the new plan over V4 dwell
classes, direct-async high-leg tags, common target, asymmetric RX geometry,
profile integrity settings, and exact plan digest.

Teach the runner and backend to serialize, claim, validate, and execute V4
intents explicitly. Keep V3 dispatch intact so an operation persisted before
cutover still resolves against its original 10/15/25 authority.

Extend the coordinator's counter-authoritative plan union with V6 and publish
it only as `RecordingManifestV7`. Add a V4 policy tag such as
`PRODUCTION_DIRECT_ASYNC_RATES_V4`; do not reuse the V3 tag. Add additive
direct-async transport evidence if necessary so the persisted recording proves
ring extension was false and DDR-ring requested/admitted/capacity values were
zero for every segment. The manifest must close over that evidence, profile
tags, controller/tuning tags, requested and applied settings, per-leg sample
counts, stream order, and synchronization.

### 4. Extend existing Standard-native admission

The analyzers already review 20 MS/s. Add the two exact direct-async 20 MS/s
profile identities and the additive V7 manifest/snapshot/binding readers needed
to reach the existing V2 native source and V5 path binding.

Retain all V3/V6 analysis gates unchanged. The V7 gate should require the new
policy tag, one dual-RX 2.5 MS/s stream, one single-RX high-rate stream, common
tuning, and one of exactly 15/20/25 MS/s. No analyzer should learn about the
radio adapter or storage paths.

### 5. Seal deployment and rollback

Update the example environment and production verifier to require the new
policy ID, feature gate, v0.46 final direct-async firmware facts, exact profile
bytes/digests, service command, and staged release revision. The verifier must
reject a missing 20 MS/s profile, the old V3 policy, a DDR-ring 20 MS/s profile,
or any accidental 10 MS/s slot in V4.

Cut over only while capture is paused and drained and there is no active radio
lease. Preserve the pre-cutover environment and exact old release. Rollback
requires the same pause/drain fence and no pending V4 operation that an older
release could not parse; V3 recordings and queued operations remain supported
by the new release throughout.

## Verification ladder

1. **Contracts and schedule:** round-trip every new contract; reject digest,
   rate, RX, target, profile, and policy tampering; prove every cycle contains
   two of each class; sample many operation keys to exercise both radios, both
   RX inputs, every channel/edge, and both tandem modes.
2. **Profiles and buffer geometry:** validate unique profile revisions and
   assert that 20 MS/s resolves to 1,145 frames and 18 direct-async segments.
   Prove V3 remains 10/15/25 and V2 remains DDR-ring-capable.
3. **Acquisition:** use fake radios to produce V7 manifests for 15, 20, and 25
   MS/s. Cover exact readback, explicit no-ring readback, final-frame drain,
   inter-segment gaps, cancellation, writer failure, peer failure, storage
   admission, and quarantine. Never publish a shortened or unclosed stream.
4. **Operational vertical:** parameterize the real-PostgreSQL bounded capture
   test over 15/20/25 and verify capture, manifest registration, Standard-native
   jobs, PNG inventory, repository views, and API responses.
5. **Compatibility:** parse immutable manifests V1-V6 and execute persisted
   intents V1-V3 without changed semantics. Golden scientific fixtures do not
   move merely to satisfy the new tests.
6. **Deployment:** test environment rendering, service templates, staged-file
   digests, ring-free direct-async firmware attestation, rejection of any
   DDR-ring profile/fallback, and fail-closed cutover checks. PostgreSQL and
   hardware tests keep explicit markers.

## Bounded hardware canary

No RF collection is part of implementation or ordinary CI. After the software
and deployment gates pass, obtain explicit authorization for one bounded
canary. Cover the only new transport geometry with four 60-second 2.5+20 MS/s
captures: each radio once as the high-rate radio on RX0 and RX1. This is four
minutes of RF time and remains well below the repository's 30-minute ceiling.

For every canary, require:

- exact requested/applied 2.5 and 20 MS/s rates, bandwidths, RX geometry, and
  maximum-coverage tuning;
- 1,145 returned high-rate frames across 18 distinct generations;
- direct-async ring extension false and every DDR-ring requested, admitted,
  capacity, and capture value equal to zero on every segment;
- counter-derived returned span, missing samples, inter-segment loss, and
  drained tail that close arithmetically;
- no queue enqueue failure, truncation, unexplained overflow, or peer-only
  publication;
- a verified V7 bundle on the local recording store, never a write beneath
  `/mnt/qnap01`; and
- one successful Standard-native reprocess through stored artifacts and the
  browser/API view.

Only after the canary receipt is accepted should production switch to V4.
Observe the first complete six-dwell bag, confirm two captures of each requested
pair and healthy processing backpressure, then leave the normal supervisor in
control. Do not turn validation into a separate long-running RF campaign.

## Completion criteria

The work is complete when the new release can schedule and persist exactly
2.5+15, 2.5+20, and 2.5+25 MS/s pairs; all three flow through Standard-native
and the Web UI; V1-V3 intents and V1-V6 manifests remain readable; the bounded
20 MS/s hardware canary is accepted; and the production cutover and rollback
checks both fail closed.
