# DS2 capture inventory protocol

The inventory is frozen at the exclusive UTC cutoff stored in `manifest.json`.
It includes an adaptive session only when its `captured_at` lies on
2026-09-24 UTC and is strictly before that cutoff.  `recorded_at` and
`finalized_at` do not decide membership.

The inventory reads only two local public API resources:

1. paginated adaptive-history metadata; and
2. the existing analysis-status record for each in-window session.

It does not open IQ, trigger analysis, alter queue state, or read/write QNAP.
The protected `scanner-adaptive-recordings` namespace was inaccessible to the
inventory user, so capture-time fixture mappings and geometry digests are
recorded as unavailable.  The builder never substitutes radio identity or a
dual-RX analyzer configuration for an explicit geometry binding.

Raw-capture eligibility requires UTC qualification, completion, an attested
source span, nominal 300-second duration, at least one retained visit, and an
analysis status declaring RX0/RX1.  Analysis-ready eligibility additionally
requires a completed public analysis status that explicitly supplies a track
count.  Geometry-aware model eligibility requires the binding itself, so no
DS2 scan currently receives that label from this inventory.

Track and signal counts remain null when the public status has not exposed an
explicit count.  They are not estimated from visit count, duty cycle, or GLRT
configuration.

Completed tracking readiness is read separately from the authoritative
`/api/v1/scanner/tracking/{session_id}` endpoint and saved as the DS2 backfill
companion `tracking-readiness.json`.  It preserves this manifest's frozen
membership and cutoff while binding the actual sealed tracking product.
