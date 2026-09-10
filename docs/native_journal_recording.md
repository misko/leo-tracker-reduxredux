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
separate evidence and remain unqualified here.

## Review with retained source binding

When the producer supplies a separate
`starlink-glrt-native-source-binding/v1` artifact, add its path and expected
file digest:

```sh
python -m leo.cli.native_journal_recording \
  --recording /absolute/path/native-recording.json \
  --sha256 EXPECTED_EXPORT_SHA256 \
  --source-binding /absolute/path/native-source-binding.json \
  --source-binding-sha256 EXPECTED_BINDING_SHA256 \
  --output /absolute/path/new-bound-review-directory
```

Both binding options are required together. The application checks the binding
digest and its closed contract, then matches the export digest, raw journal
digest, epoch and result counts. Every native pilot must fall inside its bound
coarse source coordinates. Unsupported endpoints, the excluded receiver,
invalid boot IDs, malformed geometry and false signed/precision claims fail
before an output directory is created.

This produces the distinct `native-journal-bound-application-review/v1` schema;
the original unbound schema is unchanged. The source metadata, original runtime
result and owner status remain in the summary. A negative runtime result stays
negative even when source correspondence passes. `radio_boot_source_bound`
means the explicitly retrospective retained-owner correspondence described in
the nested binding; it is not a fresh radio query or signed hardware proof.

The bound CSV adds scheduled start, refined start and pilot-center times relative
to output sample zero of the coarse recording. Calculations subtract integer
native coordinates before division; the 1,272-sample group delay is already
included in the binding origin and is not subtracted again. These times are
receiver sample-axis coordinates, not UTC or resolved physical frame epochs.
Automatic publication, artifact registration and display in the recording UI
remain subsequent integration work.
