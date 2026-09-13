# Radio .20: passive coarse observer component

A new bounded C observer can continue measuring saved coarse IQ after startup
using a separate copy of the accepted coarse history. It is implemented in
firmware-worktree commit `1c98073aa2f061bb4b94f2a80a1bb4138fb36473` and has
passed host tests, independent real-IQ replay checks and synthetic component
cases on radio `.20`'s ARM. It is **not yet integrated into the live receiver**
and does not feed observations into the native controller.

This follows the [native filter diagnosis](2026_09_13_radio20_native_filter_diagnosis.md).
The purpose is to measure whether coarse support persists during native
operation and loss before designing any policy that combines the two histories.
The existing native acceptance gates and prediction horizon are unchanged.

## Behavior and bounds

The observer runs its calculations at 2.5 MS/s and measures one 3,300-sample
pilot every nine frames, or 12 ms. The caller supplies the existing retained-IQ
owner, four pinned reference phases, a monotonic clock, cancellation and a
synchronous retention callback. It performs no allocation, radio configuration,
FPGA submission or native-controller update.

Every measurement must come from a valid copied source window. Its exact IQ,
software moments and estimate are retained before the observer's independent
history advances. Cancellation, source validity and wall time are checked again
after retention. A retained record followed by terminal failure is not a
committed history point; callers must retain the terminal status and count too.
Numerical work and retention callbacks run outside the capture-owner mutex.

The observer permits at most 200 measurements and five seconds each of wall
time and source look-ahead from its first predicted pilot. It retains the
existing eight-support requirement, 96-frame fitting window and
last-supported-plus-32 prediction limit. WAIT creates no measurement, and DONE
or a failure requires reinitialization. The original startup/native history is
never modified by the observer.

## Real-IQ replay

The replay imports the actual history retained by the previous ARM startup
qualification and continues on that qualification's original 2.5-second
positive recording. This is a different recording from the later 509-head
native run; it does not prove what coarse support did during that native loss.

| Host replay case | Measurements | Supported | Terminal result |
| --- | ---: | ---: | --- |
| Unmodified real-IQ continuation | 37 | 29 | History no longer supports the next prediction |
| Synthetic zero-IQ dropout after the same real handoff | 3 | 0 | History no longer supports the next prediction |

The real continuation observes frames 1062–1386; its final supported frame is
1359. The next scheduled frame, 1395, would exceed the unchanged 32-frame
horizon. The dropout control leaves the last-supported frame at 1053 and stops
before predicting frame 1089.

Both cases use the actual C observer and owner-copy path. Every retained IQ
window is compared with its input samples; all forty moment records are checked
independently. The 37 nonzero-input fits also receive independent dense numerical
checks. The zero-input control is checked against the explicit zero-energy
rejection. The imported history remains byte-for-byte unchanged.

Elapsed source time is modeled with a declared 2.5-ms processing cost per
measurement: 444.5 ms for the real continuation and 36.5 ms for the dropout.
These are **modeled replay times**, not ARM performance measurements. The
zeroed continuation is explicitly synthetic and does not modify the original
recording or any golden fixture.

## Tests and physical ARM check

The host run passes 140 component tests, including 34 observer cases plus
existing IQ-owner, live-bootstrap and trend tests. Observer coverage includes
all four reference phases, large absolute sample indexes, overwritten or closed
IQ, source/clock faults, cancellation, retention failure and finite budgets.
A publication-order test checks that a legitimate source update between clock
and owner reads is accepted using a fresh clock read after the copied view.

The same 34 synthetic cases pass on the physical ARM of
`1040005e0b100007100010000bf33a5d4d` at `192.168.1.20`. The executable opens no RX
buffer and submits no native jobs. It builds with Cortex-A9/NEON optimization
and warnings treated as errors; its SHA-256 is
`0bccb9bc2727c6584669ac8bf96a95df17631da8a71c52e7c7915609e236f610`.
Before/after attestation matches, TX remains disabled, and the operator removes
its temporary files. The resident 60-MS/s image and boot
`f685a28f-a5da-47ec-a03e-bfd111d7ab70` remain unchanged.

No RF was collected in this work. Next is receiver integration with a separate
retention path and measured concurrent load, followed by checking coarse support
through actual native loss. This component alone does not qualify native
precision, continuous tracking, autonomous LO revisits or refinement.

The [evidence manifest](figures/2026_09_13_radio20_passive_coarse_observer/evidence.json)
contains the real-IQ replay records, synthetic ARM case results, source/build
hashes and host test receipt. Original artifacts remain beneath
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/`.

