# Publication of the reviewed local report backlog

This archive publishes all **129 Markdown files** identified as missing in the
[2026-09-28 inventory](../2026_09_28_local_report_inventory/README.md), together
with selected supporting evidence and available documentation dependencies.
Original report bytes are preserved. Later publication does not turn exploratory
results into confirmation or historical operating instructions into current policy.

The [publication manifest](publication-manifest.json) records every copied file's
SHA-256, size and source timestamp, plus deliberately omitted artifacts. This
is a portable evidence archive, not a full RF/payload backup or deployment.
No new scientific fits, RF collection, production changes or recovery commands
were run to publish it.

## Reading order and disposition

| Batch | Entry points | How to read the publication |
|---|---|---|
| Dataset continuity | [DS8](../2026_09_28_ds8_post_ds7/README.md), [DS7 annotations](../2026_09_27_ds7_satellite_annotations/README.md), [DS7/DS8 correspondence](../2026_09_28_ds7_ds8_correspondence/README.md) | DS8 has 65 sealed recordings and 65 pose companions. Annotation tables are reference-conditioned candidate hypotheses, not decoded satellite identities. The linked correspondence study is a separate bounded investigation. |
| Scientific strategy | [Strategy review](../2026_09_27_subkm_strategy_review/REVIEW.md), [later DS7 result](../2026_09_27_ds7_full88/REPORT.md) | Preserve the strategy review as a pre-full88 snapshot. The later complete pooled result is 677 m against an exposed unsurveyed reference. |
| Hardware interpretation | [RX0 floor and repair](../2026_09_26_rx0_floor/README.md) | Hardware regime affects which reception comparisons are interpretable. |
| Receiver geometry | [Current comprehensive summary](../2026_09_27_rx_geometry_comprehensive/README.md), [direction feasibility](../2026_09_27_roof_direction_subset/REPORT.md), [disjoint confirmation](../2026_09_27_rx_disjoint_confirmation/RESULTS.md) | Keep the newer comprehensive report on main. Original experiments are now available at their original paths; the latest disjoint confirmation failed its progression gate. |
| Geometry development history | [Initial feasibility](../2026_09_27_roof_geometry_evaluation/REPORT.md), [location model](../2026_09_27_roof_location_geometry/REPORT.md), [confirmation](../2026_09_27_roof_geometry_confirmation/RESULTS.md), [balanced confirmation](../2026_09_27_roof_balanced_confirmation/RESULTS.md), [transfer diagnosis](../2026_09_27_rx_transfer_concentration/README.md) | Protocols, amendments, numerical failures and later development are retained. Their chronological status is not changed by this archive. |
| Earlier DS5 model history | [Joint mixture](../2026_09_26_joint_mixture/FULL_DS5_REPORT.md), [probabilistic model](../2026_09_26_ds5_probabilistic/REPORT.md), [Reno diagnosis](../2026_09_26_reno_track_audit/REPORT.md), [residual models](../2026_09_26_residual_polynomial/REPORT.md) | Read final reports alongside the preserved protocols and comparator results. Flexible residual fitting and low RMS do not establish satellite identity. |
| Signal/header investigations | [DS7 latest recovery](../2026_09_27_ds7_header/DATA_RECOVERY.md), [UT reference experiment](../2026_09_27_ut_header/README.md), [scan diagnosis](../2026_09_27_scan_60d9d1e77c14da0a/CAREFUL_DIAGNOSIS.md) | Template structure and recurring bit patterns are distinct from parsed identity, position, UTC, FEC or payload recovery. |
| Performance engineering | [PLUTO+ overview](../2026_09_27_plutoplus_static_arm/REPORT.md), [later optimization](../2026_09_27_plutoplus_static_arm/optimize/GOAL40.md), [server benchmark](../2026_09_27_server_scan_speed/REPORT.md) | Saved-file and bounded contention measurements are not integrated live-feedback or sustained recording guarantees. Historical runbooks are archived, not executed or promoted into current operating policy. |
| Operational history | [Publication recovery](../2026_09_27_adaptive_publication_recovery/RECOVERY.md), [receiver palette deployment](../2026_09_27_rx_marker_colors/DEPLOYMENT.md) | Dated receipts remain dated receipts; unfinished recovery notes are not relabeled as completed work. |
| Historical tables and specifications | [DS6 proposal](../2026_09_27_ds6_proposal/TABLE.md), [timestamped prior tables](../2026_09_27_sac_reno_last24/TABLE.md), [GLRT scoring specification](../2026_09_28_ds7_glrt_benchmark/SCORING.md) | Proposal/snapshot tables are not current dataset authorities. The scoring specification is published without the ongoing benchmark's changing implementation or run outputs. |

## What is included and what remains local

- The DS8 membership seal and all bound pose files are included. Offline verification
  checks the DS7 parent, disjoint IDs/digests, counts, time boundaries and pose hashes.
  Both datasets are exposed single-site research corpora; publication of these pose
  files does not provide a blind-location test set.
- DS7 annotation HTML, CSVs, summary evidence and figures are included despite
  their original ignored `local/` paths. The HTML can be downloaded for local
  interactive viewing. Its host-specific preparation index and redundant script
  intermediate are omitted.
- Header figures and compact numerical/provenance receipts are included. IQ,
  waveform arrays, soft-symbol arrays and caches remain local. Original receipts
  can name omitted files and absolute paths; those historical hashes are not a
  claim that this publication contains every original artifact.
- Performance summaries, comparisons, validation receipts and source snapshots
  are included. Executables, build/work directories, profiling dumps and most
  per-case performance shards are omitted. Original experiment receipts describe
  their historical external toolchains; the archive is not a self-contained build.
- Large Sacramento/Reno API snapshots remain local; timestamped tables and CSVs
  are included. The [frozen DS7 prior aggregation](../2026_09_27_ds7_publication/prior-aggregation/README.md)
  remains the comparison for that dataset.

Statements such as “data remain ignored” or “no data committed” inside the
original reports describe their experiment-time state. This publication exports
selected derived evidence afterward; it does not change the original scientific
claims. Raw source captures remain in their existing storage.

## Reconciliation with existing main

Six different local Markdown files were older than, or formatting-equivalent to,
their existing main versions; main was preserved. The local follow-up correction
to the [timing/FPGA review](../2026_09_12_timing_frequency_resolution_and_fpga_review.md)
was checked against the already-published radio qualification report and merged
as a narrow correction: 10,463 historical returned measurements, 10,431 supported,
approximately 14 seconds of historical feedback, and three fresh handoffs from
eight accepted cases in the later ARM test. This is not a new experiment.

The original backlog inventory is retained as a historical snapshot. It should
not be read as the current unpublished-work list after this archive lands.
New work created after that snapshot, including the active GLRT benchmark, is
outside this publication except for available dependencies explicitly listed
in the publication manifest.

## Publication validation

All 129 reviewed missing Markdown files retain their original exported bytes.
The 1,149 copied evidence files match their publication-manifest SHA-256 values,
and relative Markdown links resolve to included files or existing main content.
DS8's offline verifier confirms 65 recordings and DS7+DS8 membership of 153;
the strategy review's 1,287-asset inventory hash also verifies. Three annotation
tests and two server-comparison tests pass. These checks validate the publication
and selected helpers, not a fresh replication of every archived experiment.
