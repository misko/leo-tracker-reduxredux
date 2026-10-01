# Published experiment bundle

This publication contains the full-scan cutoff-disabled experiment, its preceding
missing-detection diagnosis and rolling-backfill prototype, and the saved
baseline observations, detector receipts, shared evaluator, and qualification
results needed to inspect those comparisons.

The qualified research tracker source and component-owned tests are included at
`native/adaptive/tracking/research/streaming_rolling_backfill/`, with its shared
type header. The detector change is preserved as the diagnostic report's
`source-change.patch` and hash-bound build/source receipts. The runtime detector
configuration was not changed or activated by publishing this bundle.

Local compiled executables, object files, build caches, raw IQ, and the redundant
large `server-tracks.json` serialization are omitted. The server's track TSV,
source maps, and per-dwell receipts are included. Saved raw IQ and the documented
local toolchain/runtime dependencies are required to repeat hardware execution.

Original qualification manifests intentionally retain hashes of local artifacts,
including omitted binaries; they are historical execution receipts, not promises
that every listed file is published. `PUBLISHED_FILES.sha256` is the inventory of
files included in this publication, excluding itself. Scientific fixtures and
scoring thresholds are published as they were evaluated, without modification.

This commit is based directly on remote main. Unrelated work and unpublished
commits on the shared workspace branch are not included.
