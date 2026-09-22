# Completed phase and geometry analysis reports

This publication contains the completed phase/geometry reports and their supporting saved-analysis artifacts from research commit [660bd85a](https://github.com/misko/leo-tracker-reduxredux/commit/660bd85a). It preserves both positive results and negative controls. Earlier reports document intermediate estimators; read the corrections and completion audits before interpreting their phase measurements as physical evidence.

## Start here

- [Every-sample dual-RX phase plot](2026_09_22_per_sample_dual_rx_phase.md): raw and frequency/delay-compensated samples within a strong paired GLRT probe, with a 50-sample zoom and CSV.
- [GLRT-guided observed receiver phase](2026_09_21_glrt_guided_broadband_phase.md): explicit phase references, uncertainty, frequency-change guidance, and guided versus unguided results.
- [Full captured-bandwidth alignment](2026_09_21_full_bandwidth_rx_alignment.md): fractional delay, frequency/drift, channel response, synthetic recovery, and held-out IQ validation.
- [Geometry completion audit](2026_09_21_geometric_phase_completion_audit.md): what the evidence establishes and what remains unresolved about geometric attribution.
- [LT3D-001A geometry audit](2026_09_21_lt3d001a_phase_geometry_audit.md) and [phase-change geometry scenarios](2026_09_21_phase_change_geometry_scenarios.md).
- [Stable-LNB single/double-difference assessment](2026_09_21_stable_lnb_double_difference_assessment.md).

## Track and estimator investigations

- [Recent eight-hour long-track inventory and phase analysis](2026_09_21_recent8h_long_track_phase.md).
- [6ad long-track phase](2026_09_21_scan_hop_6ad_long_track_phase.md) and [phase connection audit](2026_09_21_long_track_phase_connection_audit.md).
- [28d dual-RX phase](2026_09_21_scan_hop_28d_dual_rx_phase.md), [raw-IQ audit](2026_09_21_scan_hop_28d_raw_iq_phase_audit.md), and [overlap-tracklet phase](2026_09_21_scan_hop_28d_overlap_tracklet_phase.md).
- [28d simultaneous double-difference cohort](2026_09_21_scan_hop_28d_simultaneous_dd_cohort.md) and [bootstrap](2026_09_21_scan_hop_28d_simultaneous_dd_bootstrap.md).
- [28d matched-pilot double differences](2026_09_21_scan_hop_28d_matched_pilot_dd.md) and [cohort](2026_09_21_scan_hop_28d_matched_pilot_dd_cohort.md).
- [Matched-pilot noise control](2026_09_21_matched_pilot_double_difference_noise_control.md) and [geometry curvature check](2026_09_21_geometric_phase_curvature_check.md).
- [34c0 visit 678 matched-pilot investigation](2026_09_21_scan_hop_34c0_visit678_matched_pilot_dd.md).
- [Shared-residual phase-half audit](2026_09_21_shared_residual_phase_half_audit.md) and [20-visit validation](2026_09_21_shared_residual_phase20_validation.md).
- [Historical local-phase report and correction](2026_09_21_adaptive_dual_rx_local_phase.md), with the [raw-authority negative control](2026_09_21_bfc60_raw_authority_negative_control.md).

## Reproduction provenance

Report commands refer to the research checkout, not necessarily the runtime source currently on `main`. To reproduce these analyses, use the pinned research commit above in a separate checkout, the recorded environment/dependencies, and the saved IQ authorities named in each report. The JSON artifacts retain source/manifest hashes where provided. Raw radio recordings remain in their original storage and are not part of this publication.

This publication changes only `reports/`; it does not integrate the research branch's application changes or authorize a production deployment.
