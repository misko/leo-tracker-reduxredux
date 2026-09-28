# Outstanding local report inventory

Snapshot: 2026-09-28T00:37:19.769452+00:00.

This compares the original workspace's report Markdown recursively with the proposed main publication, including the full DS7 evidence chain. It does not publish the outstanding report directories.

**37 report locations contain 129 Markdown files absent from the publication and 7 files with different bytes.** Locations include directories and standalone reports. 498 local Markdown files match the publication exactly.

Different bytes do not automatically mean unpublished work: the original checkout may contain an older version than main. Those entries need review before any replacement.

This is a path-and-content inventory, not a count of independent scientific studies or finished reports. Protocols, nested evidence, copied sources, and progress notes are included. A missing original may already be represented by a published summary—for example, the receiver-geometry comprehensive report contains snapshots of several original studies.

| Local report location | Missing Markdown | Different Markdown | Example files |
|---|---:|---:|---|
| `2026_08_21_scanner_burst_duty_cycle.md` | 0 | 1 | `2026_08_21_scanner_burst_duty_cycle.md` |
| `2026_08_24_frame_cfo_estimator_study.md` | 0 | 1 | `2026_08_24_frame_cfo_estimator_study.md` |
| `2026_08_25_d3_pilot_filter_prototypes.md` | 1 | 0 | `2026_08_25_d3_pilot_filter_prototypes.md` |
| `2026_09_12_timing_frequency_resolution_and_fpga_review.md` | 0 | 1 | `2026_09_12_timing_frequency_resolution_and_fpga_review.md` |
| `2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle.md` | 0 | 1 | `2026_09_14_eight_hour_rx0_10msps_pss_glrt_tle.md` |
| `2026_09_14_radio20_five_300s_30ms_tracking.md` | 0 | 1 | `2026_09_14_radio20_five_300s_30ms_tracking.md` |
| `2026_09_26_association_soft_prototype` | 2 | 0 | `REPORT.md`, `comparison.md` |
| `2026_09_26_ds5_0850_diagnosis` | 2 | 0 | `HISTORICAL_TIMING_DISTRIBUTION.md`, `REPORT.md` |
| `2026_09_26_ds5_probabilistic` | 1 | 0 | `REPORT.md` |
| `2026_09_26_independent_soft` | 1 | 0 | `REPORT.md` |
| `2026_09_26_joint_location_prototype` | 2 | 0 | `REPORT.md`, `comparison.md` |
| `2026_09_26_joint_mixture` | 6 | 0 | `ADDITIONAL_RESULTS.md`, `FULL_DS5_FINDINGS.md`, `FULL_DS5_REPORT.md` |
| `2026_09_26_penalized_joint` | 1 | 0 | `REPORT.md` |
| `2026_09_26_reno_track_audit` | 6 | 0 | `FURTHER_DIAGNOSIS.md`, `NUISANCE_REPORT.md`, `PROBABILISTIC_PROTOTYPE.md` |
| `2026_09_26_residual_polynomial` | 3 | 0 | `REPORT.md`, `REPORT_1250.md`, `SMALL_TIMING_REPORT.md` |
| `2026_09_26_rx0_floor` | 2 | 0 | `README.md`, `repair-verification.md` |
| `2026_09_27_adaptive_publication_recovery` | 3 | 0 | `PAGINATION_DEPLOYMENT.md`, `RECOVERY.md`, `TRACK_REVIEW_CAP_DEPLOYMENT.md` |
| `2026_09_27_ds6_proposal` | 1 | 0 | `TABLE.md` |
| `2026_09_27_ds7_header` | 3 | 0 | `DATA_RECOVERY.md`, `README.md`, `RECOVERY.md` |
| `2026_09_27_ds7_satellite_annotations` | 1 | 0 | `README.md` |
| `2026_09_27_plutoplus_static_arm` | 14 | 0 | `CONCURRENT_SCAN_BENCHMARK.md`, `EXAMPLES.md`, `PROTOCOL.md` |
| `2026_09_27_roof_balanced_confirmation` | 40 | 0 | `ASSOCIATION_TRANSFER_PROTOCOL.md`, `CALIBRATION_RATIO_DISPERSION.md`, `CANDIDATE_MIXTURE_CALIBRATION_DESIGN.md` |
| `2026_09_27_roof_direction_subset` | 2 | 0 | `PROTOCOL.md`, `REPORT.md` |
| `2026_09_27_roof_geometry_confirmation` | 9 | 0 | `AMENDMENT_SOURCE_TOPOLOGY.md`, `BALANCED_DEVELOPMENT_PROTOCOL.md`, `BALANCED_DEVELOPMENT_RESULTS.md` |
| `2026_09_27_roof_geometry_evaluation` | 2 | 0 | `PROTOCOL.md`, `REPORT.md` |
| `2026_09_27_roof_location_geometry` | 6 | 0 | `BASELINE_AUDIT.md`, `DIAGNOSTIC_GAUSSIAN.md`, `PROTOCOL.md` |
| `2026_09_27_rx_disjoint_confirmation` | 3 | 0 | `PROTOCOL.md`, `REGRESSION_DIAGNOSIS.md`, `RESULTS.md` |
| `2026_09_27_rx_geometry_comprehensive` | 0 | 2 | `EXPERIMENT_LOG.md`, `README.md` |
| `2026_09_27_rx_marker_colors` | 1 | 0 | `DEPLOYMENT.md` |
| `2026_09_27_rx_transfer_concentration` | 4 | 0 | `CONSERVATIVE_RESULTS.md`, `GROUPED_REBUILD_RESULTS.md`, `RANDOMIZED_REBUILD_PROTOCOL.md` |
| `2026_09_27_sac_reno_last24` | 4 | 0 | `TABLE.md`, `refresh-074632/TABLE.md`, `refresh-084709/TABLE.md` |
| `2026_09_27_scan_60d9d1e77c14da0a` | 2 | 0 | `CAREFUL_DIAGNOSIS.md`, `REPORT.md` |
| `2026_09_27_server_scan_speed` | 3 | 0 | `REPORT.md`, `cache-audit.md`, `acquisition_peak/README.md` |
| `2026_09_27_subkm_strategy_review` | 1 | 0 | `REVIEW.md` |
| `2026_09_27_ut_header` | 1 | 0 | `README.md` |
| `2026_09_28_ds7_glrt_benchmark` | 1 | 0 | `SCORING.md` |
| `2026_09_28_ds8_post_ds7` | 1 | 0 | `README.md` |

[Exact file inventory](inventory.json). Data-only report directories without Markdown are outside this inventory; no statement is made about their publication status.

The full DS7 upload preserves original report/seal bytes, including historical failed attempts. It includes the minted dataset metadata, proposal, evaluation setup, waves 1–9, full88, bound source/configuration files and tests. Raw IQ and externally stored observation/bank artifacts referenced by absolute paths are not bundled. Two historical bytecode files are retained solely because a wave-3 closeout explicitly hashes them; they are not runtime requirements.

Publication checks: 2,879 historical file bindings verified, all original full88 report links resolve, 89 DS7 component tests plus two frequency-unit tests passed. Original CSV line endings and historical whitespace are retained to preserve hashes; the legacy artifacts therefore retain Git whitespace warnings. No new scientific fits or RF collection were performed.
