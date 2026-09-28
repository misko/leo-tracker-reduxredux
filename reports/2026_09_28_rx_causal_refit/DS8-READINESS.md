# DS8 readiness for the next independent assessment

## Finding

DS8 is ready for a bounded derived-cache preparation. The public
`ScannerTrackingInputStore` successfully loaded the deterministic earliest recording at each
of 2.5, 5, 7.5, and 10 Msps. Each loaded object is the persisted public contract
`leo.contracts.scanner_tracking.TrackingInput`; its input-manifest hash matches the sealed DS8
capture, and each has a saved analysis-manifest hash and 4,430–4,438 probes. This check read
derived objects only. It did not read IQ, inspect candidates or outcomes, or run a detector.

The missing stage is cache packaging, not a new GLRT. The existing roof-confirmation pattern is:

1. Load each selected session through `ScannerTrackingInputStore(/srv/bulk/leo)`.
2. Validate `qualified`, the sealed input-manifest hash, complete visit membership, unique probes,
   and simultaneous RX counterparts.
3. Serialize the unchanged public object with pickle protocol 5 to an exclusive local path and
   record its SHA-256, analysis-manifest hash, rate, and counts.
4. Emit a `ready: true`, `split: evaluation` inventory for `tools/rx_paired_opportunities.py`,
   plus the existing pose and snapshot-authority bindings required downstream.

The implementation pattern already exists in
`reports/2026_09_27_roof_geometry_confirmation/select_confirmation.py cache` and
`reports/2026_09_27_rx_disjoint_confirmation/cache_inputs.py`. A DS8-specific wrapper should
bind the sealed DS8 manifest and refuse overwrite. Running that wrapper is deliberately outside
this metadata audit.

## Conditional four-rate panel

Before any new outcome inspection, select the earliest DS8 capture at each rate, breaking ties by
session ID:

| Rate | Session | Capture start UTC ns | Derived status |
|---:|---|---:|---|
| 2.5 Msps | `scan-fw-226485b45dd0d0cf` | 1790526179074988475 | TrackingInput load verified |
| 5 Msps | `scan-fw-ac05824a99b22ffd` | 1790525754014558201 | TrackingInput load verified |
| 7.5 Msps | `scan-fw-aadcd44b66085469` | 1790525329519835170 | TrackingInput load verified |
| 10 Msps | `scan-fw-9c5f3143152db63d` | 1790527027918045168 | TrackingInput load verified |

All four have terminal-complete capture metadata, qualified UTC, both receivers, no transport
loss, and pose revision `gauss-r20-roof-20260926-v1`. They are strictly post-DS7 and disjoint from
the 14 receiver-geometry recordings. The 7.5 Msps row was used in DS8 rate validation. The DS8
10 Msps population was screened in the correspondence study, and corpus membership has been
public throughout. The other two are not claimed to be historically untouched because absence of
a repository mention does not prove absence of inspection.

[`ds8-readiness.json`](ds8-readiness.json) records the exact conditional membership, input and
analysis hashes, pose bindings, and probe counts. The older four-record proposal remains useful
as a reuse panel, but it should not be presented as the next fresh confirmation. Preparing this
DS8 panel is the preferred next independent assessment. This metadata audit did not package the
panel, run association analysis, modify configuration, or collect RF.
