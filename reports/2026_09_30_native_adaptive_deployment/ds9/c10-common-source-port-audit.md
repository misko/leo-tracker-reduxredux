# C10 common source-port audit

## Decision

The scanner cannot safely accept `leo_usb_source *` in place of
`leo_local_source *`.  The two types differ in more than transport:

- the local source supplies a coherent current hardware-counter snapshot before
  every policy decision;
- Fast Lock recall supplies an exact post-transition counter boundary plus a
  profile identifier, nonzero compiled-profile CRC and actual frequency;
- local DMA blocks have an exact counter domain and exact numeric gap accounting;
- the qualified scanner and detector require two simultaneous coherent receivers;
  and
- the local application owns firmware reservation, radio preparation, prime and
  restoration outside the scanner.

The portable USB core instead permits provider-estimated counters and a software
delivery ordinal.  The ordinal counts only sample-times returned by the adapter;
it cannot reveal loss before delivery and is never a hardware clock.  The generic
Soapy backend currently advertises one receiver, no hardware counter and no
post-retune counter boundary.  It therefore cannot satisfy the current scientific
scanner preflight.  Treating its ordinal as a current counter, making a zero CRC,
or assuming that a successful `setFrequency` flushed queued samples would create
false timing and tuning authority.

The minimal safe change is an additive, transport-neutral port over an already
opened and primed source.  Existing local scanner entry points and their ABI stay
unchanged.  A later generic scanner entry consumes the new port and emits a new
event envelope with explicit authority; it does not reinterpret scanner-v2
events in place.

## Proposed C boundary

Add `native/adaptive/device/source/source_port.h` and a small validating C11
implementation.  The port deliberately has no open, close, ownership, radio
preparation or restoration operations.  Those remain application concerns and
retain their existing failure recovery.

```c
typedef struct leo_source_port {
    uint32_t abi_version;
    void *context;
    const struct leo_source_ops *ops;
    struct leo_source_capabilities capabilities; /* fixed at init */
    uintptr_t outstanding_lease;                 /* wrapper-owned */
} leo_source_port;

typedef struct leo_source_ops {
    int (*capabilities)(void *, struct leo_source_capabilities *);
    int (*position)(void *, struct leo_source_position *);
    int (*select)(void *, const struct leo_source_selection *,
                  struct leo_source_transition *);
    int (*next)(void *, struct leo_source_block *);
    int (*release)(void *, struct leo_source_block *);
    int (*cancel)(void *); /* the sole concurrently callable operation */
} leo_source_ops;
```

The fixed capabilities include:

- CI16 sample/receiver/I/Q layout, sample rate, receiver count and maximum block;
- simultaneous/coherent receiver flags;
- counter authority: software-delivered, provider-estimated or provider-exact;
- position semantics: coherent-current snapshot or last-delivered watermark;
- optional provider time authority, retained as provider time and never named UTC;
- exact-gap, selection, valid-selection-boundary and cancellation support; and
- separate frequency, target/profile and compiled-profile-CRC attestations.

`position` returns a coordinate plus its authority and semantics.  A delivered
watermark is sufficient for deterministic fake or recorded replay policy, but it
does not establish a physical revisit interval.  Only a provider-exact,
coherent-current source is eligible to be bracketed by the existing live
counter-to-UTC `Timebase`; even then, an actual measured clock bracket is still
required.  Recorded counter/UTC metadata is a separate immutable replay input and
must not be replaced by the replay host's current clock.

`select` takes a logical target key, requested frequency and explicit tolerance.
Its receipt states which values the source attested and whether
`previous_valid_end`/`valid_start` form a valid boundary in the selected counter
domain.  A multi-target scanner must reject a source without a valid boundary.
Frequency-only USB retune never becomes profile/CRC attestation.  A fixed-tune,
single-target replay can use a separately declared no-transition path, but that
must not be generalized to live retuning.

`next` returns a borrowed normalized block with first/end coordinates, block
sequence, lease token and explicit overflow/discontinuity/exact-gap flags.
`missing_samples_before` is valid only with exact-gap authority.  Unknown loss
marks a visit incomplete and increments a discontinuity/overflow count; it does
not manufacture a numeric missing-sample count.  A common clip helper intersects
a normalized CI16 block with a validity interval without copying it.

All operations except `cancel` run on the one acquisition owner.  `position` and
`select` are invalid while a block is leased.  `cancel` may run concurrently to
interrupt `next`.  Every successful `next` has exactly one `release`, including
sink, detector, validation and deadline failures.  Positive callback statuses
are normalized to `-EIO`.

## Adapters

### Local PLUTO+

Add `native/adaptive/device/local/local_source_port.{h,c}`.  It maps:

| Common operation | Existing local operation |
|---|---|
| `position` | `leo_local_source_snapshot` |
| `select` | `leo_local_source_recall` |
| `next` / `release` | `leo_local_source_next` / `leo_local_source_release` |
| `cancel` | `leo_local_source_cancel` |

It advertises provider-exact counters, coherent-current position, exact gaps,
frequency/profile/CRC attestation and a valid selection boundary.  Blocks remain
zero-copy.  The adapter neither closes the source nor restores the radio.  The
first implementation accepts and copies the immutable `leo_local_config` used to
open the opaque source, then validates every returned block against that copy.
An additive read-only local-source descriptor can later remove this caller/config
trust boundary without changing the common port.

### Portable USB and replay

An exact dual-receiver USB fake can implement the common port when it supplies a
valid retune counter receipt.  The current public USB API is otherwise usable for
blocks: its explicit exact/estimated/software authority, stream ordinal,
overflow, discontinuity, time metadata and lease already map directly.

The adapter must reject multi-target operation if `leo_usb_source_retune` does
not return `LEO_USB_RETUNE_VALID_COUNTER` in the chosen coordinate domain.  A
future software-ordinal USB provider would also need an explicit guarantee that
retune flushes all old-frequency samples before the core stamps the current
ordinal as the boundary.  Generic Soapy provides no such guarantee, so it stays
unsupported by the scientific scanner until a device-specific provider proves
the boundary and coherent dual-RX capability.

A replay adapter can implement the port directly:

- counter-bearing recordings use their recorded exact coordinate and recorded
  timing authority;
- raw-only replay uses a software delivery ordinal and cannot project UTC; and
- fixture metadata, rather than filenames or saved server candidates, supplies
  target and transition authority.

## Additive scanner integration

Keep `LEO_SCANNER_ABI_VERSION == 2`, `leo_scanner_run` and
`leo_scanner_run_timed` unchanged.  Add a separate
`native/adaptive/scanner/scanner_source.h` only after source-port review.  Its
entry point should take the common port plus explicit requirements:

- required counter/position authority;
- required selection attestations and frequency tolerance; and
- whether delivered-watermark replay is allowed.

There must be no implicit downgrade.  A live composition requests exact current
position, exact gaps, valid transition boundary, coherent dual RX and its needed
attestations.  A replay test may explicitly allow a delivered watermark, and its
result stays timing-unqualified.

The generic sink should receive a new envelope containing the existing scanner
event plus counter authority, position semantics, transition attestation,
discontinuity flags and `physical_counter_qualified`. This field describes the
source coordinate only; it does not attest UTC or end-to-end revisit timing.
Detector events retain the
visit's envelope through the queue.  A separate generic stats envelope adds
overflow, unknown-discontinuity and exact-missing counts.  This avoids silently
placing software ordinals in persisted scanner-v2 fields whose consumers assume
the local exact-counter composition.

Internally, scanner acquisition can then depend on the six port calls.  The
legacy functions construct a strict local adapter and use a sink shim that emits
the identical v2 events and stats.  The existing timed counter callback remains
local/exact until a generic measured-bracket contract is separately designed.
The application `live.cpp` remains unchanged in the first integration: firmware
reservation, local radio preparation, prime, cleanup and restoration must not be
moved into the common port.

## Concrete file plan

First additive slice:

- `native/adaptive/device/source/source_port.{h,c}`
- `native/adaptive/device/source/build.sh`
- `native/adaptive/device/local/local_source_port.{h,c}`
- `tests/native_adaptive/device/source/test_source_port.c`
- `tests/native_adaptive/device/local/test_local_source_port.c`
- additive build targets for the two new archives/tests

Reviewed follow-on, after the port is frozen:

- `native/adaptive/scanner/scanner_source.h`
- an internal source-neutral acquisition engine in `scanner.cpp`, with unchanged
  legacy wrappers
- `tests/native_adaptive/scanner/test_scanner_source.cpp`
- an exact-boundary USB adapter and fake-provider tests
- a replay adapter only when its fixture authority schema is fixed
- scanner, USB and top-level README updates

## Required tests

The source-port core tests malformed capabilities, positive-status normalization,
one-lease ownership, release on validation failure, overflow-safe CI16 byte
validation and clipping, exact gaps, unknown discontinuities and concurrent-safe
cancellation semantics.  The local adapter test covers current snapshot,
profile/CRC/frequency receipt, counter rollover boundary, zero-copy block mapping,
numeric gap preservation, clip, release and nonownership of source close.

Before a generic scanner entry can be accepted, component tests must also prove:

1. legacy local entry points emit identical event/stat bytes and retain all
   existing scanner tests;
2. an exact dual-RX fake port produces the same policy choices, windows, detector
   calls and scientific output as the local fake;
3. software ordinal replay is explicitly timing-unqualified, never reaches
   `Timebase`, and never reports an unknown gap as a number;
4. overflow/discontinuity makes the visit incomplete and suppresses feedback and
   detector submission;
5. one-RX, noncoherent, missing-boundary and missing-attestation sources fail
   before policy selection;
6. a blocked `next` is cancelled at the wall deadline and every leased block is
   released on all exits; and
7. host, sanitizer and ARM builds pass without hardware.  Any real USB test keeps
   its explicit hardware marker and separate device/model qualification.

## Implemented scanner follow-on

The reviewed follow-on is now implemented by `scanner_source.h` and the shared
engine in `scanner.cpp`. The original scanner ABI, event structure, and local
entry points remain unchanged. The local shim reads the immutable configuration
from the already-open source, then uses the same common port engine under the
strict exact-counter capability profile. The generic interface uses an additive
event and stats envelope so software-delivered ordinals, absent time authority,
transition attestations, overflow, and unknown discontinuities remain explicit.
Its `physical_counter_qualified` bit is limited to provider counter semantics;
it is not a UTC or end-to-end revisit claim.

CPU-only fake-provider coverage on host, ASan/UBSan, ARM/QEMU, and the physical
PLUTO CPU compares exact dual-RX generic and legacy
policy, window, detector, event, and stats behavior; checks malformed profiles
and missing capabilities before selection; verifies explicit weak ordinal and
zero-CRC operation remains unqualified; suppresses detector work after overflow
or unknown discontinuity; and exercises blocked cancellation plus retained
release failure cleanup. The local wrapper has an explicit terminal transfer:
after a second provider-release failure, it disposes only adapter bookkeeping
while the caller-owned local source retains the lease for its mandatory close.

This work does not qualify a USB model, UTC mapping, RF behavior, or live
scientific composition. The selected USB adapter and physical hardware profile
remain open. A DS9 recorded-source scanner replay also remains open because no
persisted source-port block/transition authority schema has been frozen; the
test does not reinterpret saved candidate rows as source blocks or invent a
live clock.

## Compatibility constraints

- Published persisted contracts and scientific goldens do not change.
- The common source is caller-owned and already open/primed; application cleanup
  order remains transport-specific.
- Scanner numerical admission remains 2.5 MS/s, two coherent receivers and the
  existing detector capability checks.  Portability does not imply one-RX
  detector support.
- No scanner core link dependency on SoapySDR is introduced.  A Pi binary links
  its selected USB provider and adapter at composition time.
- Device timestamps remain device timestamps.  Host arrival, queue latency and
  software ordinals never become UTC.
- Replay timing qualification comes only from recorded authority.  Running replay
  on a correctly set host clock does not add authority.
- Live local qualification does not transfer to USB.  Each concrete USB model,
  driver, counter behavior, retune boundary, dual-RX coherence and cleanup path
  requires separate evidence.

## Implemented first slice

The transport-neutral port core and exact local adapter described above are now
implemented.  Scanner, application and USB source code remain unchanged.  The
core validates immutable capabilities, counter/position authority, every
transition receipt and every borrowed block.  It normalizes positive callback
statuses, enforces one lease, and retains the complete borrowed block if release
fails so `leo_source_port_cleanup` can retry it.  A failed selection callback or
any invalid receipt poisons the port: the tuner may already have changed, so only
cancel and lease cleanup remain safe before composition-level recovery.

The local adapter maps exact snapshots, Fast Lock selection receipts and DMA
blocks without copying IQ.  It preserves exact numeric gaps and exposes no time
authority.  Its copied-open-config trust boundary is tested fail-closed: a false
receiver count makes common validation reject the block, and a simulated first
release failure retains the lease until an explicit successful cleanup.

Host and ASan/UBSan runs passed both the source-port and expanded local-source
fake suites.  ARM cross-compilation passed.  Reproduce them with:

```sh
native/adaptive/device/source/build.sh host /tmp/leo-source-port-host
native/adaptive/device/source/build.sh sanitize /tmp/leo-source-port-san
native/adaptive/device/source/build.sh arm /tmp/leo-source-port-arm
native/adaptive/device/local/build.sh host /tmp/leo-local-port-host
native/adaptive/device/local/build.sh sanitize /tmp/leo-local-port-san
native/adaptive/device/local/build.sh arm /tmp/leo-local-port-arm
```

The frozen ARM test artifacts are in `builds/arm-source-port-v1/`:

| Artifact | SHA-256 |
|---|---|
| `test-source-port` | `ec3f7d545320e9fb67a7f2b4cad3eaa256c6b7c876086ec1ffd3fb587b005463` |
| `test-local-source` | `00163c255f46224c80d2801d017ab911a75f1c8b9b9760c589db3ceb9241493f` |
| `libleosourceport.a` | `0a402fb4d3ffab5f6570269c01a25addadd96a862caac76502f22cc36c305add` |
| `libleolocalsourceport.a` | `8402dca090339f51e1861076134ffe75ec93d2ea7270d2d8e995e94a62721615` |

The matching binaries passed on the physical ARM CPU from
`/tests/source-port-ec3f7d54`.  `test-source-port` exited zero in 0.004315632 s
wall / 0.004028 s CPU with 796 KiB maximum RSS.  `test-local-source` exited zero
in 0.003860568 s wall / 0.003576 s CPU with 856 KiB maximum RSS.  The
[physical receipt](c10-source-port-arm-receipt.json) records the hashes and
explicitly states that both are injected-fake tests: neither opened local/USB
hardware nor performed RF capture.

The source hashes at this boundary are:

| Source | SHA-256 |
|---|---|
| `source_port.h` | `554a7b5640eb5582b384a0ea4a7d6c6848bcaaf5762c2d17664fb208c277e4a5` |
| `source_port.c` | `688493b3c406539ca80b25fb65ffeeb68cf97713c96c25f3a841c8c6b89073ef` |
| `local_source_port.h` | `f9b4621ecb6745a2fe0e22d015b72163f206f15230a9c05b4ff6d4d5902eb316` |
| `local_source_port.c` | `0383044dd7f9f21078238008b1d4425052ec9dcdb43a5a8ceb645b4d94ebea72` |

Those source hashes precede only this report text.  No USB adapter is included in
the first slice: the public generic Soapy path cannot provide current position,
coherent dual RX or a valid retune boundary.  An exact fake can exercise a future
adapter once its boundary/query API is fixed; no field will be synthesized merely
to admit it.  The generic scanner engine and event envelope remain reviewed
follow-on work, so this is source-port scaffolding rather than completed Pi or
scanner integration.

This work performed no hardware or RF operation and changed no scanner,
application or USB-device source.
