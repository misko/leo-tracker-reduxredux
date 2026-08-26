# Response-blind Doppler holdout selector v2 preregistration

**Date:** 2026-08-26

**Phase:** feasibility revision only; frozen before execution
**Response state:** future odd-Qin outcomes remain unopened

## Decision being frozen

This revision asks whether the exact 15 `holdout_foundation` captures can supply
at least ten capture-level masks on which fixed 500 ms, fixed 125 ms, and causal
20 ms estimators can later be compared. It will not run those estimators and it
will not read, demodulate, or score an odd-Qin response.

The input is the exact response-blind v1 derived manifest, file SHA-256
`sha256:860b067a154b6b5ecf3172aa2f18105d4ef753cdb5472bab44cbfe9339662c70`
and semantic digest
`sha256:c82a548683cbdfd026420ace9c8b6161ba5b69331682d6c68c1baafd73410b39`.
That manifest already binds all 15 recording and Standard-analysis manifests,
300 required product receipts, source trajectories, aliases, epochs,
counter-contiguous episodes, and even-Qin frame masks. V2 reuses those choices
byte for byte. It performs no dynamic discovery and needs no `/srv` access.

## Why v1 is being revised

V1 required 600 supported frames, 65% episode-wide density, and a 75-frame
contiguous run anywhere in a 1.5 s episode. Those gates measured global signal
density, not whether a particular future target had enough strictly past
support for all three estimators. The v1 even-only diagnostics may inform this
revision because the odd-Qin response remains sealed. This makes v2 a declared
feasibility-informed revision, not a pristine first protocol.

V2 replaces the indirect global gates with direct, per-target support gates.
Every eligible target must itself pass the frozen even-Qin mask and must have,
in the same continuity segment and strictly before the target:

| History | Minimum supported frames | Minimum supported span |
|---:|---:|---:|
| 20 ms | 8 | 10 ms |
| 125 ms | 50 | 62.5 ms |
| 500 ms | 200 | 250 ms |

The counts are one common approximately 53% occupancy rule applied to the
nominal 750 Hz opportunity count in each window. The span is one half of each
horizon, preventing a dense but temporally concentrated clump from supplying a
rate fit. These rules do not use CFO error or any odd-Qin value.

A capture is evaluable only with at least 75 such targets spanning at least
250 ms. The later comparison must use exactly this identical target mask for
all estimators. Every opportunity, including failures and overlapping failure
reasons, will be retained.

## Stop rule

If at least 10 of the exact 15 captures pass, the derived cohort and masks will
be frozen and this lane will stop. Passing does not authorize response opening
by this lane; it only supplies a reviewable input for the separately frozen
calibrated-estimator comparison. If fewer than 10 pass, all failures are
retained and the holdout remains sealed.

No capture may be substituted. No newer, PRE-FIX, 3/5-MS/s capture-only,
`Research`, or current experimental recording is permitted.
