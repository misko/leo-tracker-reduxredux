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
Registration and display in the recording UI use complete published bundles,
as described below.

## Review a published bundle

For automatic operator publications, select the final manifest and its expected
digest instead of naming separate recording and source-binding files:

```sh
python -m leo.cli.native_recording_bundle \
  --manifest /absolute/path/published-episode/manifest.json \
  --sha256 EXPECTED_MANIFEST_SHA256 \
  --output /absolute/path/new-review-directory
```

The application requires the complete version 1 bundle manifest and exactly
its seven declared artifacts. It verifies each byte count and digest, rejects
symlink/nonregular payloads and path traversal, and checks agreement between
the manifest, recording and source binding. This includes the radio/boot/visit/
epoch, owner outcome, raw journal length, source-file hashes and external coarse
IQ reference. Raw owner evidence is retained and hash-checked, not interpreted
through a dependency on commissioning code. The coarse IQ is external to this
bundle; its digest refers to the producer's retained source validation.

A directory without the final manifest, a partial publication, an inconsistent
or changed artifact, or a mismatched source produces no application review.
The output remains the existing bound-review schema and CSV. Publication
completion does not replace the preserved runtime result or owner status.
The reusable bundle reader is also the admission point for recording UI integration.

## Register a publication for the API and UI

```sh
python -m leo.cli.native_recording_register \
  --manifest /absolute/path/published-episode/manifest.json \
  --sha256 EXPECTED_MANIFEST_SHA256 \
  --registry /srv/bulk/leo/native-recordings
```

Registration verifies the complete bundle before atomically publishing one
small local record of the absolute manifest path and expected digest. Payloads
are not copied. Identical registration is idempotent; a conflicting existing
registration is rejected. The manifest digest is the public recording ID.
New registry directories use mode 0755 and registration records use mode 0644
so the separate API account can read them even when the producer has a private
umask. Existing ancestors are not changed. The selected manifest and payloads
must also be readable by that account; new native publications provide those
permissions explicitly. Earlier private publications are not modified by
registration and can be republished to a new accessible directory. Use a fresh
registry when an existing ID points to the old private location; registration
does not replace existing mappings.

Production reads `LEO_NATIVE_RECORDING_REGISTRY`, defaulting to
`LEO_BULK_ROOT/native-recordings`. A missing registry is an empty list and is not
created by the API. New registrations become visible on the next refresh.
There are no HTTP registration or filesystem-path parameters.

* `GET /api/v1/native-recordings?cursor=0&limit=20` lists registered episodes.
  The maximum list page is 100. Damaged or missing payloads remain listed with
  `integrity_unavailable` and no summary; they are not silently omitted.
* `GET /api/v1/native-recordings/ID?cursor=0&limit=200` returns the bound summary
  and measurements. The maximum measurement page is 1,000. Every request
  revalidates publication bytes. Missing IDs return 404; registered evidence
  that fails verification returns 409. Both routes support HEAD.

The **Native refinement** tab shows per-episode run outcomes, support/rejection
counts, radio/boot/epoch identity, exact native counters, CFO, and timing
corrections. The CFO plot contains only supported fits on the current page;
the table retains rejected estimates and rejection/fault masks. It does not
connect across gaps, concatenate epochs, fit Doppler rate, or claim acquisition
or physical accuracy qualification. Times remain on the bound receiver sample
axis. Large native counters are decimal strings throughout the browser port.

The prepared v16 operator invokes this CLI automatically after RF shutdown,
saved owner receipt and publication. It records registration outcomes separately
and preserves the original radio outcomes. The handoff is tested on retained
recordings; its live execution and deployment of this UI to the running
production service remain to be verified.
