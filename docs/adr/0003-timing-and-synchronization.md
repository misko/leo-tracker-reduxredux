# ADR 0003: Evidence-based best-effort synchronization

Status: accepted

## Decision

Two-radio synchronized acquisition uses concurrent preparation, a readiness
barrier, and a shared near-future host monotonic release target. Every stream
records observed timing brackets, timing method, counters, sequences, gaps, and
uncertainty. Cross-radio skew and overlap are derived from those observations.

The system never claims phase coherence, hardware triggering, or exact sample
alignment between independent Pluto+ radios. Signal-derived alignment is an
analysis product and cannot rewrite acquisition evidence.

## Continuity observability

Host read completion, refill sizes, and requested sample counts do not prove
device-side continuity. A stream may claim loss observability only when its
transport supplies a trustworthy monotonic sample/device counter or equivalent
sequence evidence. Without that evidence, manifests set
`sample_loss_observable=false`, guaranteed overlap is zero, and synchronization
is graded degraded even when every requested host buffer arrived and no host
gap or overflow was reported.

Qualification reports must distinguish all three statements:

1. requested and captured host sample counts matched;
2. no host-observable gap/overflow occurred;
3. device-side sample loss was not observable.

The first two cannot be summarized as “no sample loss.” Adding device-counter
instrumentation can strengthen future evidence without changing historical
manifests or reinterpreting old captures.
