# Single-RX observation and UTC-authority audit

Date: 2026-09-30

Status: bounded design audit only. No production contract or scientific policy
was changed. No hardware or RF was used.

## Question

The one-receiver scanner can now preserve single-RX detector evidence over a
software-delivered source coordinate and no Fast-Lock profile CRC. This audit
identifies the additional authority required before that evidence can become a
live `Observation` with UTC support and enter tracking/location inference.

Assumptions are deliberately narrow:

- the host system's UTC clock is correctly maintained;
- the radio supplies no device timestamp and no hardware sample counter;
- no coherent peer receiver exists;
- the source coordinate is only a delivered watermark; and
- target RF/channel/edge and source/analysis digests remain explicit caller
  authority.

Correct host UTC does not date a sample by itself. The transport delay between
physical sampling and a host timestamp must still be bounded, and sample
continuity must be attested separately.

## Reviewed source closure

| File | SHA-256 |
| --- | --- |
| `native/adaptive/timing/timebase.hpp` | `96c6990079ee4347b87e90a7a274f849f4d3707f5187f74045c37a926d75f8af` |
| `native/adaptive/timing/timebase.cpp` | `df2425f3219ba80a0c2a856e81bfae081240ce335999776c9b9bf4af5c4bd301` |
| `native/adaptive/ingest/ingest.hpp` | `1251df92214dd21f8a997871b23972f1171a8a11368ac8d9f053946fe818da62` |
| `native/adaptive/ingest/ingest.cpp` | `e8f4aa1c1de08868566fd821c95cc06b65f5747e7d8e4cb1f605652031625bd5` |
| `native/adaptive/runtime/projection.hpp` | `4cc5df3d49a64cbfb21e9ea4150ae9b630ec15ae92d8621ded2b0710aa26e995` |
| `native/adaptive/runtime/projection.cpp` | `b1a367dea74f682dd6ffec8fae7a07f503db568ebc73ab914d7d1a1233651727` |
| `native/adaptive/online/online.cpp` | `7b070bfb5b3bc8655142e55194104f6646d8e4fbef9b20d5f84f7c4ee050065f` |
| `native/adaptive/application/session.hpp` | `204668adc0e6ffd38361c7d5b325dc2d595b665ac0598ef4df83ea7f60312c7a` |
| `native/adaptive/application/session.cpp` | `a31494fb86b621c9d6f23cd5158425e42cb474337f576ba72a55efd1dc8aee75` |
| `native/adaptive/scanner/scanner_source.h` | `cbb339c40aa01bceaab43ea4080442fcb7c46fc00dcd2b89aee4c03b6a170429` |
| `native/adaptive/scanner/scanner_single_source.h` | `6fd38e335eda5639a38a876891bd99638bcf3deb9d83ac3f862c7eb9b2474818` |
| `native/adaptive/scanner/scanner.cpp` | `9bb5a1d75a2c99f25e418e618893cf8b9e363a9bcb2236184a947308e53d8f86` |

## Current fail-closed boundaries

The current components correctly reject this weaker source:

1. `timing::read_bracket` returns `unqualified_counter` before any clock read
   when `exact_counter` is false. `Timebase::observe` also rejects such a
   bracket. Its drift and reset tests assume that counter deltas represent
   physical sample time, which a software-delivered ordinal cannot establish.
2. `ingest::ProfileAuthority::live_attested` requires a nonzero prepared target
   CRC and nonzero event CRC. `historical_metadata` permits zero CRCs only for
   replay. There is no live frequency-attested/no-CRC authority.
3. `runtime::classify` requires `ProjectionSource::continuity_qualified`.
   Absence of a reported discontinuity is not sufficient to set this for a
   software ordinal.
4. Projection converts the UTC interval width into
   `hypot(400 Hz, 15000 Hz/s * width/2)`, but `online::to_candidate` drops
   `Observation::standard_uncertainty_hz`. Tracking and location therefore use
   support-center UTC without consuming that uncertainty.
5. `Session::accept` accepts a raw `leo_scanner_event`, so it cannot validate
   the source-neutral envelope's counter, position, time, transition, block,
   and physical-counter authority.

These are actual blockers. Setting `exact_counter=true`, selecting
`historical_metadata`, or setting `continuity_qualified=true` because the scan
looked intact would manufacture authority.

## Separate continuity authority is required

A software delivery ordinal counts returned sample-times. It cannot show that
the radio produced no omitted physical samples between them. The current
overflow and discontinuity flags report known failures; their absence is not a
proof that no physical sample is missing.

Retune validity and continuity are different claims. A qualified retune can
exclude samples from the old tuning while a later USB/driver gap remains
undetectable. Likewise a complete scanner dwell proves that the requested
number of delivered samples was assembled, not that the physical sampler had
no gap.

A provider can support a weaker source without an absolute hardware counter
only if it separately attests this invariant for a named capture generation:

> Every physical sample-time in an attested interval is delivered in order, or
> the provider reports a discontinuity before delivering any later sample.

That is a strong device/driver/transport guarantee. Generic Soapy overflow
reporting does not establish it. It must default to unavailable and be enabled
only for a pinned provider, driver and hardware profile with source review and
physical qualification. It does not reveal an absolute counter or the size of
a failed gap.

The narrow scanner handoff can be either:

- generation-wide continuity attestation, with the scanner ANDing authority
  over every block covering the visit; or
- per-block qualified spans, with the scanner qualifying only candidate
  20-ms supports wholly covered by contiguous spans.

The latter is weaker and more precise but requires retaining source-block span
boundaries through detector completion. In either form, use an additive source
authority sidecar or a new source-event major version. Do not reinterpret
`physical_counter_qualified`, `GAP_EXACT`, or the existing v1 envelope. The
projection bridge may set continuity qualified only from that explicit
evidence. A candidate with unknown continuity remains useful recorded detector
evidence but is not an online physical observation.

## Host-delivery UTC interval

The existing candidate event carries
`detector_enqueued_monotonic_ns`, captured on the acquisition thread after the
complete dwell has been assembled, policy feedback has run, and retained IQ is
copied into a detector slot. It is a useful upper-time observation, but it is
not the physical capture time.

Add a distinct `timing::DeliveryTimebase`; leave the exact-counter `Timebase`
unchanged. It should:

- bracket `CLOCK_MONOTONIC` against `CLOCK_REALTIME` without a source counter;
- retain a bounded generation and anchor history;
- detect realtime steps and excessive monotonic/realtime drift;
- map a past enqueue-monotonic value only within its configured anchor age;
- require a nonzero, finite maximum capture-end-to-enqueue delay; and
- carry source-rate tolerance and clock resolution into the interval.

The delay bound must include the entire path before the recorded enqueue time:
radio/device buffering, USB transfers, driver and Soapy queues, source block
tail beyond `valid_end`, capture-loop work, assembly, policy feedback, and the
dwell copy. It cannot be inferred solely from USB queue size. A provider may
make it structurally enforceable with bounded buffers, timestamped delivery,
runtime stall rejection, and a qualified scheduler profile. A merely observed
maximum is evidence, not a hard bound.

The interval arithmetic must remain one-sided. If clock correlation places the
enqueue time in `[L, U]` and physical capture-end-to-enqueue latency is in
`[0, B]`, then capture end is in:

```text
[L - B, U]
```

It is **not** `[U - B, U]`; that would discard uncertainty in the lower clock
endpoint.

For nominal dwell duration `d` and a full rate-error allowance `delta`, valid
start is conservatively:

```text
[L - B - d - delta, U - d + delta]
```

so its full width is `(U - L) + B + 2*delta`. Projection of a later support
offset grows the width again by the offset's rate-error allowance. Checked
integer arithmetic and explicit rounding are required.

A value-owned result should carry at least:

```text
generation
valid_start software coordinate
valid_start UTC midpoint
full UTC uncertainty width
sample rate and rate tolerance
authority = host_delivery_bounded
continuity authority/profile digest
capture-to-enqueue bound
```

It must never be labeled exact-counter timing. A missing latency bound, stale
clock anchor, clock step, event timestamp outside the anchor history, or absent
continuity attestation returns unavailable.

## No-CRC live observation binding

Add a third profile authority named along the lines of
`live_frequency_attested`, but accept it only through a new overload that takes
the full `leo_scanner_source_event` plus the bounded delivery timing result.
The existing raw-event overload must reject that authority.

For the one-RX path, validate all of the following:

- source-envelope ABI is recognized;
- counter authority is `SOFTWARE_DELIVERED`;
- position semantics are `DELIVERED_WATERMARK`;
- physical-counter qualification is false;
- source time authority is `NONE`;
- transition authority contains frequency attestation and a valid counter
  boundary, and contains no target, profile-CRC, or time-boundary attestation;
- target and event CRC are both zero;
- receiver is exactly zero and no peer recovery is represented;
- no overflow or discontinuity affects the qualified support;
- the explicit target index, logical profile, tuning frequency, sky RF,
  channel, and edge agree with immutable session authority; and
- input and analysis digests are valid, with the provider, continuity, timing,
  and latency-profile manifests included in the input authority.

The logical target/profile remains an application policy key. The source
attests the actual tuning frequency only. Sky RF, channel and edge come from
the immutable target map and are never inferred from frequency readback.

Return the existing numeric `Observation` together with an additive timing
authority record containing the full UTC width, authority kind, continuity
profile digest and latency bound. Do not reuse the replay-only historical
mode. The observation support center may remain the midpoint for compatibility,
but the uncertainty must survive ingestion and publication.

## Causality and downstream use

If support end is an interval, `Session` must retain its upper endpoint. At the
candidate callback the evidence certainly exists by that upper endpoint, so it
is a valid per-observation causal watermark. The lower endpoint is the
conservative source-progress value for quiet-time advancement. The midpoint
alone is neither role.

Candidate timestamps cannot advance a quiet source when there are no
candidates. Full live operation therefore needs a separate acquisition-lane
progress sidecar containing a delivered coordinate, capture-completion
monotonic timestamp, authority generation, and its latency bound. It must not
use callback publication time or current wall clock, and it must account for
in-flight detector jobs before expiry. This can be an additive scanner/source
port; the published scanner event v2 need not change.

Before current tracking/location can consume these observations, online state
must retain the timing authority and full UTC width. The smallest unchanged-
science gate is an explicit maximum permitted observation UTC width in online
configuration, with snapshot/summary provenance and fail-closed rejection.
That threshold requires a sensitivity qualification against the intended
tracking/location tolerances. It must not be chosen merely to admit the device.

If the physically achievable host-delivery width is larger than the qualified
threshold, a new versioned tracking/scoring policy must consume per-observation
time/frequency uncertainty. Increasing `standard_uncertainty_hz` alone is not
effective today because that field is dropped before reconstruction. Existing
tracking/location contracts and reference results must not be silently
redefined.

## Concrete component boundaries

No implementation is authorized by this audit. A lean staged change would
touch:

1. `native/adaptive/timing/delivery_timebase.{hpp,cpp}` and timing-owned tests
   for clock-only correlation and interval construction.
2. An additive source/scanner authority sidecar for explicit within-support
   continuity and quiet progress. Existing event/source ABI bytes remain
   unchanged.
3. `native/adaptive/ingest/ingest.{hpp,cpp}` with the source-envelope overload,
   live no-CRC authority, and value-owned timing companion.
4. `native/adaptive/application/session.{hpp,cpp}` with additive observe/accept
   overloads, upper-bound causal watermarking, and timing stats.
5. `native/adaptive/online/online.{hpp,cpp}` only after policy review, to retain
   timing provenance and enforce the predeclared uncertainty gate. A larger
   uncertainty-aware scientific policy is a separate versioned change.

The existing exact PLUTO path and historical replay path stay byte-for-byte in
behavior.

## Required tests

- Clock-only read order, transactionality, anchor expiry, UTC step, monotonic
  regression, rate drift, overflow and generation reset.
- Exact interval vectors for `[L-B,U]`, dwell translation, source-rate ppm,
  clock resolution, support offsets, and integer boundaries.
- Missing/zero delay bound, stale anchor and absent continuity return
  unavailable without changing output.
- Existing raw ingest overload rejects live zero-CRC evidence; the new overload
  accepts it only with the complete source-envelope authority matrix.
- Each forged authority bit, nonzero CRC, peer receiver, wrong target/profile/
  frequency, discontinuity, overflow and unqualified continuity is rejected.
- A source with no reported discontinuity but no explicit continuity
  attestation is rejected.
- Support-end upper bound is used for candidate causality; lower-bound quiet
  progress is monotonic and cannot pass pending detector work.
- Online uncertainty threshold accepts at/below the boundary and rejects above
  it while retaining exact authority/width in snapshot diagnostics.
- Exact-counter PLUTO and historical replay observations, IDs, supports and
  scientific outputs remain unchanged.

## Decision

The no-profile-CRC target binding is straightforward once it consumes the
source-neutral event envelope. UTC midpoint and uncertainty can be represented
with a separate bounded host-delivery timebase, but the current provider has
neither a hard capture-to-enqueue bound nor a physical continuity attestation.
The current tracking path also discards the only observation uncertainty field.

Until those three gates are addressed, the truthful Pi endpoint is saved
single-RX detector/candidate evidence, not a qualified live tracking/location
observation. No counter, UTC, continuity, CRC, or peer receiver should be
synthesized to bridge the gap.
