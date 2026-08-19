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

