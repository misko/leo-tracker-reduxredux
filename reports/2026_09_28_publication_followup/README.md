# Report publication follow-up — 2026-09-28

This snapshot publishes the reports and supporting evidence added since the
[previous publication](../2026_09_28_publication_inventory/README.md). It also
updates the dataset index to include DS9 and removes the duplicate DS8 row.
DS7, DS8 and DS9 are authorized inputs for further modeling; their frozen
membership and individual evaluation limitations still apply.

## Results and unfinished experiments

| Report | Status at publication | What the evidence establishes |
| --- | --- | --- |
| [DS7 residual transfer](../2026_09_28_subkm_residual_transfer/README.md) | Complete; already on main | Full88 diagnostics, including the unqualified independent control |
| [Shared slope](../2026_09_28_subkm_shared_slope/README.md) | Complete; already on main | First-record held-score gain; no new geographic estimate |
| [Boundary fallback](../2026_09_28_arm_boundary_fallback/REPORT.md) | Complete development report | 19,576/19,581 original hits recovered; cohort was used for tuning |
| [Semantic checkpoint](../2026_09_28_sequence_semantics/SEMANTIC_CHECKPOINT.md) | Updated research checkpoint | Negative parity searches and bounded firmware analyses; no validated decoder |
| [Expanded literature review](../../docs/research/starlink-literature/broad-review-2026-09-28.md) | Complete scoping review | Coverage and access limitations remain explicit |
| [DS8/DS9 fallback validation](../2026_09_28_arm_ds89_validation/STATUS.md) | In progress | Protocol, preparation and partial execution evidence only |
| [Slope transfer](../2026_09_28_subkm_slope_transfer/STATUS.md) | Protocol only | No seven-record fit or transfer result yet |

Publishing a protocol or checkpoint does not complete its experiment. No
additional RF collection or numerical campaign was launched for this publication.
The broader sub-kilometer modeling objective remains open.

## Integrity and publication boundary

The [manifest](manifest.json) records exact original and published hashes.
Four stale local historical Markdown variants are archived under `local-variants/`;
newer canonical remote reports are preserved. The [Markdown inventory](markdown-inventory.json)
accounts for the local report prose present at the snapshot. Concurrent research
may produce later files; these are not silently represented as part of this snapshot.

All **390 bindings** checked in the residual-transfer, shared-slope and completed
boundary-fallback indexes matched the local source artifacts. See
[integrity audit](integrity-audit.json). This does not rerun the scientific fits.
The prior publication's historical receiver-geometry README seal discrepancy
remains documented there; it has not been silently resealed.

**13 focused tests passed**: six semantic/fallback tests and seven DS8/DS9
preparation, execution and summary tests, using the installed scientific Python
environment. The workspace Python initially could not collect two tests because
SciPy was unavailable; rerunning in the scientific environment passed.

Raw IQ, generated executables, firmware images, downloaded third-party papers
and build caches remain external. Derived semantic evidence and firmware analysis
receipts are included. The source index uses public source links and records local
PDF cache paths as text, so the published review does not link to absent PDFs.

One new large numerical file is stored losslessly as `rows.jsonl.gz` beside its
original intended path in the boundary-fallback `host704-v1` directory. Restore
only that missing original with `gzip -dk rows.jsonl.gz`; its uncompressed SHA-256
is in the manifest. The earlier publication's 50 archives retain their existing
restoration procedure. Original scientific seals refer to uncompressed bytes.

This commit publishes research evidence and documentation. It does not change
the unrelated dirty application files in the shared workspace.
