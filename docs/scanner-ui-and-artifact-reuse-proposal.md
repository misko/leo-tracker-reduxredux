# Scanner UI and artifact reuse proposal

Status: design proposed; framed IQ retention implemented in this worktree

## Recommendation

Reuse the recordings UI's master-detail shell and its generic artifact display
components, but do not represent a retuned scanner sweep as one fixed-tuning
recording. Persist each scan as one framed scanner IQ bundle and adapt its
individual frames to the reusable waterfall/GLRT algorithms.

A scan and a recording have similar operator presentation needs, but they do not
have the same persisted truth:

- A recording is one fixed-tuning, durable IQ session registered in PostgreSQL.
  It has a recording manifest, one or two radio streams, analysis runs, catalogued
  products, and digest-verified Standard/Research artifacts.
- A scan is eight short sequential tunings captured before analysis. The updated
  capture path publishes one concatenated CI16 payload with authoritative
  per-frame boundaries and frequencies, while the existing standalone
  `ScannerReport` JSON remains the decision contract.

Trying to manufacture a `RecordingDetailV1` for a scan would invent a fixed
recording profile, storage paths, analysis run, and product registration that do
not exist. It would also either create eight tiny recording sessions per sweep or
misrepresent eight retunes as one continuous recording. Both choices weaken the
existing contracts.

The elegant reuse boundary is therefore:

1. shared browser layout and artifact cards in React;
2. shared pure Starlink acquisition/GLRT64 algorithms;
3. shared low-level immutable-file and PNG-writing utilities where their
   semantics really match;
4. scanner-owned metrics, artifact manifest, projection, and scientific plot
   renderer.

## What the scanner does today

The scheduled scanner is coordinated by the same acquisition supervisor and
radio authority as ordinary recordings. In the durable-queue path, each
successful scheduled recording enqueues a `scanner_sweep` immediately after the
recording operation.

For a sweep, the scanner:

1. opens the configured Pluto and attests its serial;
2. configures two receivers, 2.5 MS/s, 2.5 MHz bandwidth, manual gain, one kernel
   buffer, and a 120 ms dwell by default;
3. sequentially tunes the lower and upper edge of Starlink channels 1 through 4;
4. captures all eight two-receiver IQ blocks before doing detector work;
5. closes the radio and releases the capture lease;
6. analyzes each captured block in 20 ms windows with a 10 ms stride;
7. declares an edge active only after two same-receiver, non-overlapping hits
   pass the GLRT64 margin gate with tracking CFOs within 8 kHz;
8. atomically writes one `starlink-scan-YYYYMMDDTHHMMSSZ.json` report.

For the default 120 ms dwell, the exact probe starts are 0 through 100 ms in
10 ms increments. Adjacent windows overlap by 10 ms. The non-overlap
confirmation rule means a hit in one window cannot confirm itself through its
adjacent overlapping window.

The detector correctly reuses the reviewed symbolwise acquisition and
`conditioned_glrt64_score` numerical implementation. It deliberately does not
run Anchor-8, QAM, trajectory, or the complete Standard DAG.

## Artifacts generated today

Only one durable artifact is generated per scheduled scan: the report JSON. Raw
IQ lives only in the captured in-memory sweep. Each IQ block contributes a
SHA-256 digest to the report, but the corresponding samples cannot be retrieved
after analysis.

The report contains:

- scan and radio identity;
- the complete scanner configuration and ordered eight-target band plan;
- capture and analysis elapsed times;
- one result for every target;
- requested and applied IF, tune/listen timings, and IQ digest;
- `active`, `no_detection`, or `inconclusive` decision and reason;
- best GLRT64 margin;
- for an active edge, the first confirmed receiver/probe/candidate, acquired,
  residual, and tracking CFO, exact and control scores, and margin;
- explicit candidate-only and no-payload-decoding claims.

No GLRT64 metric series, waterfall, plot JSON, PNG, Standard subject,
analysis-run manifest, or catalogued analysis product is currently produced.
Raw IQ is now retained in a scan-native framed bundle.
The current report retains only the first confirmed hit and the best margin, so
a truthful per-window GLRT64 plot cannot be reconstructed from it.

## What the web UI exposes today

`GET /api/v1/scanner/latest` returns the newest complete report.
`GET /api/v1/scanner/reports` returns a newest-first cursor page, with each full
report embedded in its history row. The store only accepts regular, single-link,
bounded files under the approved local scanner root and fails closed on symlinks,
invalid names, invalid JSON, or files that change while being read.

The current Scanner view shows:

- history: scan time, scan ID, radio, capture/analysis runtime, active-edge count
  and names, and a complete/partial status derived from inconclusive results;
- selected-scan summary: scan ID, radio, capture time, analysis time, dwell, and
  the candidate-only/no-payload claim;
- selected results: channel, edge, decision, RF center, applied IF, best margin,
  detected receiver, tracking CFO, and reason.

It does not show the radio serial, most configuration fields, requested IF,
per-target tune/listen timing, IQ digests, probe/candidate identity, acquired or
residual CFO, exact/control scores, or first-detection margin. It has no artifact
gallery and exposes no PNG route. The browser also does not use the `latest`
endpoint; it uses the paginated history endpoint.

The history contract is convenient but inefficient for a master-detail UI. A
live check on 2026-08-21 found 108 reports. A 20-report scanner page was about
126 KiB because it embeds all results, while a 20-row recordings page was about
18 KiB. Summary and detail reads should be separated, as they already are for
recordings.

## Required scanner products

Preserve `ScannerReport` schema version 1 unchanged. Add a separately versioned,
bounded scan product bundle with these products:

### 1. GLRT64 probe metrics JSON

`ScannerGlrt64MetricsV1` should retain the evidence actually used by the
decision. For every target, receiver, 20 ms probe, and retained acquisition
candidate it should include:

- probe index and start sample/time;
- receiver ID and candidate rank;
- epoch sample;
- acquired, residual, and tracking CFO;
- exact score, control score, and margin;
- whether the margin gate passed;
- stable identifiers for both members of a confirming non-overlapping pair.

Collection bounds follow directly from the configuration. At the current
maximums, a 120 ms sweep has 8 targets x 11 probes x 2 receivers x at most 8
candidates, or 1,408 candidate rows. Contracts should enforce the configured and
absolute bounds rather than accepting unbounded lists.

The existing report remains the compatibility summary. Its decision,
`first_detection`, and `best_margin` must be validated as exact projections of
the metrics product so summary and plot evidence cannot diverge.

### 2. GLRT64 probe PNG

Publish one combined, publication-quality PNG with eight target panels. Each
panel should show:

- x-axis: probe start time, exactly 0 through 60 ms at 10 ms intervals for the
  default geometry;
- y-axis: exact-minus-control GLRT64 margin;
- distinct RX0 and RX1 series;
- the configured margin-gate line;
- markers joining the two hits that caused an active decision;
- channel, edge, applied RF/IF, and active/no-detection/inconclusive state.

This is more useful and much smaller than eight independent image files. A
single figure also makes channel comparison immediate.

### 3. Channel-activity PNG

Publish one compact four-channel by two-edge overview. Color should encode the
best margin relative to the configured gate, while a shape or explicit label
encodes the decision. Color alone must not carry active/inconclusive state.

Both PNGs must say `candidate-only; no attribution or payload decoding`. They
must be rendered from the persisted metrics/report values, never by rerunning
analysis during an HTTP request.

### 4. Scanner artifact manifest

Add `ScannerArtifactManifestV1`, keyed to the immutable report, containing the
scan ID, report digest/size, and a bounded list of product descriptors:

- artifact ID and versioned kind;
- media type;
- byte count and SHA-256;
- scanner-owned logical name;
- optional target identity for future target-specific products.

The manifest is the commit record for the product bundle. API and UI code should
consume scanner-store methods and descriptors, never construct storage paths.

## Publication layout and compatibility

Keep the existing report archive intact and use sibling IQ and artifact namespaces:

```text
scanner-reports/
  starlink-scan-20260821T150642Z.json
scanner-recordings/
  2026/08/21/scan-0123456789abcdef/
    manifest.json
    iq.ci16.zst
scanner-artifacts/
  starlink-scan-20260821T150642Z/
    manifest.v1.json
    scientific/glrt64-metrics.v1.json
    presentation/glrt64-probes.v1.png
    presentation/channel-activity.v1.png
```

The publisher should compute all bytes and digests, publish the artifact
directory without replacement, and publish the existing report file last. The
report remains the visibility/compatibility commit point. A crash can leave an
unreferenced artifact directory, but cannot expose a report whose required new
products are only partly written. Cleanup of such orphans should be added only
if measurement shows it is needed.

Existing report-only scans remain valid. Their detail projection must explicitly
say that GLRT64 metrics and PNGs were not published by that scanner version; it
must not synthesize plots from `best_margin`.

Do not write scanner products under `/mnt/qnap01`. The scanner IQ manifest is
authoritative that concatenation is a storage coordinate only: each frame keeps
its own sample range, channel/edge, requested and actual IF/RF, host timing
bracket, byte count, and digest.

## API shape

Keep both v1 endpoints for compatibility and add recordings-like v2 projections:

```text
GET /api/v2/scans?cursor=0&limit=50
GET /api/v2/scans/{archive_key}
GET /api/v2/scans/{archive_key}/artifacts/{artifact_id}
```

The list returns `ScannerSummaryV2` rows only: archive key, scan ID/time, radio,
state, active targets, target counts, and capture/analysis durations. The archive
key is the validated filename timestamp token, allowing direct bounded lookup
without scanning every JSON body to find a random scan ID.

The detail returns `ScannerDetailV2`: the full v1 report, metrics summary,
artifact descriptors, and explicit unavailable reasons for legacy products. It
does not return raw filesystem paths.

The artifact route resolves through `ScannerArtifactStore`, verifies inode,
size, digest, and manifest membership, and serves JSON or PNG with an immutable
ETag. The API adapter never opens a constructed path itself.

## UI reuse design

`App.tsx` is currently about 1,300 lines and owns the recordings browser,
scanner page, queue page, recording detail, shared primitives, and formatting
helpers. Reusing `RecordingDetail` directly would add conditionals throughout a
component whose props assume recording-only contracts.

Instead, extract these genuinely shared pieces:

- `MasterDetailWorkspace`: two-column responsive shell and detail loading/error
  behavior;
- `BrowserPane`: header, optional filters, scrollable rows/table, pagination,
  selected-row behavior, and empty state;
- `DetailHeader`, `StatusBadge`, `MetricGrid`, `DataPair`, `Panel`, and
  `KeyValueTable`;
- `PngArtifactCard` and `PngArtifactGallery`, extracted from the Standard image
  gallery, accepting a typed descriptor/URL rather than recording identifiers.

Keep domain renderers small and typed:

- `RecordingBrowser` and `RecordingDetail` adapt recording contracts to the
  shared shell;
- `ScanBrowser` and `ScanDetail` adapt scanner contracts to the same shell;
- `ScanResultTable` and `ScanConfigurationPanel` remain scanner-specific because
  their scientific meaning has no recording equivalent.

The scanner layout then naturally matches recordings:

```text
+--------------------------+----------------------------------------------+
| Scans                    | Scan heading + status                        |
| Time | state | active    | Key metrics                                  |
| ...selected row...       | GLRT64 PNG gallery                           |
| ...                      | Channel/edge results + expandable metrics    |
| pagination               | Configuration, artifact integrity, provenance|
+--------------------------+----------------------------------------------+
```

The left side should be a compact semantic table on wide screens and retain
button-row behavior on narrow screens. Selection fetches the exact detail by
archive key. Polling refreshes summaries without replacing the selected detail
unless that scan no longer exists.

The complete result row should expose every persisted v1 field. Dense candidate
metrics belong in an expandable inspector or bounded table, not in the history
row. PNG cards use the same visual language and download/open behavior as
recording Standard artifacts.

## Reuse in the Python implementation

Keep scanner analysis infrastructure-blind. Evolve the detector to return a
typed `DwellDetection` containing both its decision summary and bounded probe
metrics. Add an analysis-bundle function while retaining the existing
`analyze_scan_sweep(...)->ScannerReport` wrapper for compatibility.

Do not instantiate `StandardPlotViewV2` with fake session/subject/run values.
The Standard GLRT64 renderer assumes trajectory feedback and controlled
recording presentation bindings that do not exist for a sweep.

Share only the honest rendering mechanics:

- extract the render lock, deterministic PNG serialization, common figure
  styling, and small axis helpers from `standard_png.py` into a neutral
  presentation PNG module;
- implement `scanner_png.py` against `ScannerGlrt64MetricsV1`;
- keep Standard and scanner titles, axes, and scientific annotations specific to
  their contracts.

This avoids copied file/figure plumbing without pretending the two scientific
products are interchangeable.

## Delivery sequence

1. Add bounded scanner metric and manifest contracts plus detector tests that
   pin 20 ms windows, 10 ms stride, confirmation-pair identity, and report/metric
   consistency.
2. Add the scanner artifact publisher and deterministic renderers. Test PNG
   signatures, manifest digests, immutable conflict behavior, crash ordering,
   file bounds, and the prohibition on QNAP destinations.
3. Add summary/detail/artifact store methods and v2 API routes. Preserve v1 and
   test legacy report-only scans, corruption, symlinks, pagination, exact lookup,
   digest mismatch, GET, and HEAD.
4. Extract the shared React shell and PNG cards without changing recordings
   behavior. Add component tests for both adapters.
5. Build the scanner master-detail composition and Playwright coverage for
   selection, polling, pagination, active-channel labels, full metrics, PNGs,
   legacy-unavailable artifacts, and mobile layout.

## Acceptance criteria

- A 120 ms dwell produces exactly eleven probe starts per target at 10 ms spacing.
- Every active decision identifies two non-overlapping, same-receiver,
  CFO-consistent metric rows.
- Report summary, metrics JSON, both PNGs, manifest, API detail, and UI state all
  identify the same scan and decisions.
- The left pane lists scans without transferring every full report.
- Selecting a scan displays all report fields, bounded GLRT64 metrics, active
  channels, artifact metadata, and both PNGs.
- Existing recordings UI behavior and public v1 persisted contracts are
  unchanged.
- Existing report-only scans remain browsable with truthful unavailable-product
  messages.
- Neither scanner analysis nor presentation imports PostgreSQL, HTTP, the CLI,
  or concrete recording storage.
- No scanner code writes beneath `/mnt/qnap01`.
