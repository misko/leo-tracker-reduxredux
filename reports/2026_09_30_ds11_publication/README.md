# DS11 full report publication

This publication contains the [complete DS11 ten-method report](../2026_09_30_ds11_single10/README.md), [all 320 single-scan results](../2026_09_30_ds11_single10/TABLE.md), PNG/SVG visualizations, CSV/JSON metrics, protocols, scripts, tests, input metadata, recovery records and the [87-recording dataset manifest](../2026_09_30_ds11_post_ds10/local/manifest.json).

The previously unpublished [DS10 comparison report](../2026_09_30_ds10_single10/README.md) and [parent dataset](../2026_09_29_ds10_post_ds9/README.md) are included so the comparison and DS11 boundary have their supporting evidence on main. Existing remote reports and production implementations are preserved.

## Integrity and storage

All **1,859 experiment-time evidence bindings** across the two benchmark seals and two mint seals verified before publication. The archive includes **1,838 selected report/evidence files** from the research workspace. All retain their exact bytes except the DS10 mint README, whose unrelated unpublished-report link was replaced by a publication note; its original bytes are retained under `historical-reports/`. Original and published hashes are recorded in [publication-inventory.json](publication-inventory.json). The independent publication seal [evidence.sha256](evidence.sha256) covers all included report files, this audit and the changed documentation index pages. All 38 focused admission and metric tests passed, both minted datasets verified in this checkout, and the DS11 median/P90/sub-km metrics were independently recomputed from all 320 fit records; see [validation.json](validation.json).

The **32 orbit-bank NPZ files (2,211,674,683 bytes)** remain in the local research workspace, following the existing report-publication convention. [local-inputs.json](local-inputs.json) records each path, size and SHA256. Raw radio recordings remain referenced in their original store. Numerical fit results, exported observation JSON, bank metadata, dataset membership and analysis receipts are published; the original experiment seals still bind the omitted binaries. A Git clone alone therefore supports reading and recomputing reported metrics, but does not contain every input needed to rerun scientific fits.

Statements in the frozen experiment reports saying “local,” “Git-ignored,” “not committed,” or “no remote publication” describe the experiment's pre-publication state. This publication explicitly includes the selected textual evidence beneath `local/`; its original paths and seals remain unchanged.

## Exact implementation snapshots

[historical-sources/](historical-sources/) preserves the exact eleven model-source files named by the benchmark plus its input exporter. The shared-slope and shared-curvature source files differ from current main. The snapshots preserve the tested implementations without overwriting newer remote source. Historical absolute paths and installed-runtime paths are provenance records, not portable clone paths. A replay must restore the listed local binary inputs, map paths to its own workspace and use the archived implementation versions. It must not silently rerun with newer model code.

The results remain unchanged: 320/320 selected fits qualified, with 937/960 qualified starts. The original independent Student-t model has the lowest DS11 median reference distance, 2759 m; correlated q020 has the lowest P90, 7217 m. Distances use an unsurveyed reference, and no dependable sub-kilometre accuracy is established. This publication performs no new scientific campaign or RF collection.
