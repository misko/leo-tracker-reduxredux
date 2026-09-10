# Inspecting radio-native refinement recordings

The application consumes the additive
`starlink-glrt-native-journal-recording/v1` JSON export without importing the
radio firmware repository. The exporter is a separate producer; copy its
closed artifact and expected SHA-256 through the recording handoff.

Run this application command with the expected digest of the **export file**,
which is distinct from the raw journal digest contained inside it:

```sh
python -m leo.cli.native_journal_recording \
  --recording /absolute/path/native-recording.json \
  --sha256 EXPECTED_EXPORT_SHA256 \
  --output /absolute/path/new-review-directory
```

The command checks file integrity, the versioned port, finite numeric fields,
exact integer widths, descriptor/sample/carrier association, frame order,
terminal counters, rejection accounting and clearance. It writes a summary
and a CSV containing every retained result, including rejected fits. Existing
output directories are refused. Invalid input is rejected before creating
the output directory. A summary is written only after the CSV is complete.

The CSV preserves native sample indexes as decimal strings. Relative times
are calculated by subtracting integer indexes before division, retaining
sub-sample resolution even for source counters beyond 2^53. Unsupported fits
remain visible but do not enter the summary's supported CFO range. No rate
estimate is computed from rejected samples or across epochs.

This is an offline review adapter. It does not assign a radio, boot, UTC axis,
capture ID or physical frame epoch to the journal. The output explicitly
reports `radio_boot_source_bound: false` and has no runtime success claim.
A file hash verifies expected bytes, not acquisition provenance. Acquisition,
solver replay, original native-IQ verification and physical precision require
separate evidence and remain unqualified here. Source binding, artifact
registration and display in the recording UI are subsequent integration work.
