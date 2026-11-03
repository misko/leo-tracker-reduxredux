# Recorded DS9 scanner-to-Analysis composition design

## Scope

This is a design for an offline, sequential composition of already recorded
DS9 dwells.  It is not a replay of the adaptive policy.  The target choice,
ordering, dwell and source-counter boundaries already occurred in the recorded
session.  The new path must reuse the profiled scanner's source acquisition,
window assembly, corrected geometry, detector execution and event delivery,
then feed one persistent `application::live::Analysis` instance.  It must not
read or inject persisted candidates, candidate IDs, supports, tracks or
location answers.

The existing adaptive runner cannot be used once per visit.  Its policy starts
each invocation at visit zero and uses a local target index.  Rewriting those
values after the fact would collide `source_group_id` values and would omit the
recorded visit from the geometry authority digest.  Running all targets at once
is also invalid: the policy may request a target or ordering different from the
saved recording.  A source adapter must reject such a mismatch rather than
silently return another target.

## Additive scanner contract

Use a separate versioned recorded-plan entry point rather than a mode flag in
scanner ABI v2.  A value-owned plan contains a session authority and ordered
visit rows.  The entry point bypasses only SPF target selection and feedback;
it reuses the existing source-port requirement checks, block acquisition and
clipping, `WindowAssembler`, geometry callback, immutable detector slot,
executor, result validation and source-event sink.

The session portion contains:

- ABI version, recorded session identifier/digest, scanner session and stream
  generation;
- sample rate, receiver count, sample layout and recording-manifest SHA-256;
- the exact public timing anchor: device counter, UTC-before, UTC-after,
  monotonic-before and monotonic-after, timing qualification and bracket
  width;
- one calibration-manifest SHA-256 and an immutable target table; and
- a plan digest over the session fields, target table and every visit row.

Each visit row contains:

- original `visit_index`, global target index and source profile/target key;
- requested tuned IF, attested actual tuned IF and maximum allowed error;
- decision/selection counter, invalid-start/previous-valid boundary,
  transition-before, transition-after, valid-start and exclusive valid-end
  counters;
- dwell milliseconds and expected sample count per receiver;
- device event sequence, device event ID and device flags needed to bind the
  public event;
- canonical recording-event SHA-256, raw CI16 SHA-256 and raw byte count; and
- a read-only public-store reference consisting of session ID and visit index.

Rows must have unique, strictly increasing original visit IDs and valid-start
counters, nonoverlapping valid intervals, exact target-table matches, a dwell
of 120/240/360 ms, and counter differences equal to sample rate times dwell.
The adapter must validate the public event and raw hashes before publishing the
plan.  Runtime selection, transition and returned blocks must equal the row.
Any mismatch fails before a detector job.  Gaps between selected historical
rows are declared plan omissions; they are not shifted counters and are not
reported as continuous capture.

Historical DS9 metadata has no live Fast Lock CRC attestation.  The plan,
source requirements and emitted events therefore carry CRC value zero and omit
the CRC-attested flag.  They retain exact provider counters, target/frequency
attestation, simultaneous coherent dual-RX layout, exact within-visit gaps and
the recorded valid-selection boundary.  No current host time supplies UTC.

## One calibration record

The exporter must create one immutable calibration record from public source
authority and maintained frequency/template contracts.  Both
`CorrectedGeometryProfile.targets` and `ingest::Authority.targets` are derived
from this same record.  A target contains:

- target index and source profile key (`fastlock_slot` for this recording);
- channel and edge;
- requested and actual tuned IF;
- sky RF center;
- per-receiver pilot IF;
- exact template minimum and maximum offsets; and
- explicit absence of a historical profile CRC.

For DS9, each of the four target indices has one constant requested/actual IF
and the fast-lock slot equals the target index.  The calibration manifest is
bound into the corrected-geometry port manifest and the Analysis algorithm
identity.  This prevents independently maintained geometry and ingest target
maps from drifting while still keeping candidates and answers out of the
authority input.

## Timing and Analysis

Construct one caller-driven `Analysis` for the complete recorded plan.  Set
`ingest::Authority::profile_authority` to `historical_metadata`, use the
recording manifest as `input_digest`, and use an analysis digest that binds the
native detector build, corrected profile, support profile and calibration
manifest.  The timing maximum age must explicitly cover the recorded plan
span.

Before any candidate event, call `Analysis::observe` once with the exact public
capture bracket:

- counter: `timing.session_start_device_sample_counter`;
- UTC bounds: `first_sample_earliest_utc_ns` and
  `first_sample_latest_utc_ns`; and
- monotonic bounds: `begin_before_monotonic_ns` and
  `begin_after_monotonic_ns`.

These are saved capture measurements, not the replay host clock.  Candidate
support UTC is then derived from the unchanged original valid counters.  The
recorded runner emits the original visit and global target index directly, so
the existing projection identity formula remains valid.  Detector enqueue,
start and finish monotonic fields continue to describe the replay execution,
and are not substituted with recorded time.

## Public DS9 inputs

The plan exporter reads only the read-only
`leo.storage.adaptive_hop.AdaptiveHopIqStore` session
`scan-fw-3cfdaa6d75762cad`, its capture manifest, the selected raw visits, and
maintained frequency/template contracts.  For each row it re-reads the public
event and CI16 values and binds both hashes.  The capture manifest currently
binds stream generation `4263234`, 7.5 MS/s dual-RX IQIQ layout, the initial
counter/UTC bracket, and all recorded event counter/RF fields.  Candidate and
analysis documents are not plan inputs.

The first bounded case is original visit 301: channel 1, lower edge, target
index/profile key 0, requested and actual tuned IF 960 MHz, 120-ms interval
`[1247949437197, 1247950337197)`, and the public event/raw hashes re-read during
export.  It is a positive representative but that outcome is not encoded in
the plan.

The second case uses the already frozen 32-visit selection in
`ds9/corrected-full-replay-v1/selection.json`.  Selection used the first two
visits in each channel by recorded receiver-outcome stratum before corrected
native execution.  The runner plan drops those outcome labels and sorts the 32
visit IDs by original valid-start counter.  It therefore covers four channels,
64 receiver windows and the recording's lower edge only.  This is sequential
recorded-dwell composition; it does not claim feedback, revisit cadence or
closed-loop policy equivalence.

## Validation gates

Component tests must establish:

1. Plan shape, digest, ordering, overlap, target/calibration, dwell and counter
   checks complete before source acquisition.
2. A requested target/frequency or returned transition differing from the row
   is rejected before raw delivery; counters are never renumbered.
3. Event/raw/manifest hash mismatch, truncated data, in-window discontinuity,
   exact gap, release failure and cancellation all fail closed and drain joined
   detector work before return.
4. Historical events have zero CRC and no CRC-attested flag.  Target and
   frequency flags cannot be manufactured or retained after a value is
   overwritten.
5. The exact persisted timing bracket reaches Analysis; changing the replay
   host clock has no effect.  Original visit IDs and target indexes reach
   projection, and duplicate run-local identities are impossible.
6. Corrected geometry receives the original recorded visit authority and the
   same calibration-manifest digest used by ingest.  A digest mismatch fails
   before capture.
7. Visit 301 scanner candidates match the corrected full-replay detector
   receipt in every non-timing scientific field, rank, gate and deterministic
   outcome counter.  Zero candidates remain a valid result in later panels.
8. The 32-visit panel compares all 64 receiver rows and retained candidates,
   then the persistent Analysis observations/tracks, against the independently
   exported corrected-native products.  Comparisons reject nonfinite values;
   they do not import reference IDs, moments or candidates into the run.

Host, sanitizer and thread-sanitizer component tests precede an ARM
cross-build.  The first visit and 32-visit host runs remain bounded; hardware
execution is root-owned.  No RF, QNAP mutation, CLI default, production release
or full 2,215-visit run belongs to this slice.

## Remaining boundary

This closes the recorded source-to-scanner-to-Analysis path for saved dwells.
It does not demonstrate that the current adaptive policy would choose the same
targets, order or dwell extensions, nor does it establish live UTC authority
for a future USB source.  Those require separate live source and closed-loop
policy evidence.
