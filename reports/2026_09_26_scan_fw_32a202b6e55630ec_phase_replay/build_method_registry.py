"""Generate the complete, execution-neutral 30-row replay ledger."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

METHODS = [
    (
        "01",
        "integrated-cfo-boundary-bridging",
        "Integrated CFO boundary bridging",
        "frame-methods",
        [
            "tools/report_within_segment_frame_phase.py",
            "reports/2026_08_22_within_segment_frame_phase.md",
            "reports/2026_09_23_longarc_phase_transport.md",
        ],
    ),
    (
        "02",
        "frame-local-qin-phase",
        "Frame-local Qin phase",
        "frame-methods",
        [
            "tools/report_frame_local_phase_qualification.py",
            "reports/2026_08_22_frame_local_phase_qualification.md",
        ],
    ),
    (
        "03",
        "adjacent-frame-correlation",
        "Adjacent-frame correlation",
        "frame-methods",
        [
            "tools/report_within_segment_frame_phase.py",
            "reports/2026_08_22_within_segment_frame_phase.md",
            "reports/2026_09_23_long_dwell_phase_change.md",
        ],
    ),
    (
        "04",
        "prompt-phase-linear-doppler",
        "Prompt phase versus integrated linear Doppler",
        "frame-methods",
        [
            "tools/report_pnt_phase_doppler_comparison.py",
            "reports/2026_08_22_pnt_phase_doppler_comparison.md",
        ],
    ),
    (
        "05",
        "five-state-phase-feedback",
        "Five-state phase feedback",
        "frame-methods",
        [
            "tools/report_pnt_kalman_comparison.py",
            "tools/report_pilot_pnt_kalman.py",
            "reports/2026_08_22_pnt_kalman_comparison.md",
        ],
    ),
    (
        "06",
        "ordinary-2pi-long-tracking",
        "Ordinary 2pi long tracking",
        "frame-methods",
        [
            "reports/2026_08_22_kalman_phase_tracking_comparison.md",
            "reports/2026_09_21_long_track_phase_connection_audit.md",
            "reports/2026_09_23_longarc_phase.md",
        ],
    ),
    (
        "07",
        "full-qin-phase-slope",
        "Full Qin phase slope",
        "frame-methods",
        [
            "tools/report_subsecond_pilot_structure.py",
            "reports/2026_08_22_edge_pilot_phase_slope.md",
            "reports/2026_08_22_subsecond_pilot_structure.md",
        ],
    ),
    (
        "08",
        "offline-binary-pi-batch",
        "Offline binary-pi batch fit",
        "frame-methods",
        [
            "tools/report_five_dwell_modulo_pi_qualification.py",
            "reports/2026_08_23_five_dwell_modulo_pi_qualification.md",
            "reports/2026_09_22_postfix_phase_methods.md",
        ],
    ),
    (
        "09",
        "causal-modulo-pi-filter",
        "Causal modulo-pi filter",
        "frame-methods",
        [
            "tools/report_five_dwell_modulo_pi_qualification.py",
            "reports/2026_08_23_five_dwell_modulo_pi_qualification.md",
            "reports/2026_09_24_consolidated_phase_methods.md",
        ],
    ),
    (
        "10",
        "five-state-modulo-pi-pnt",
        "Five-state modulo-pi PNT",
        "frame-methods",
        [
            "tools/report_pilot_pnt_kalman.py",
            "reports/2026_08_22_pilot_pnt_kalman.md",
            "reports/2026_09_22_postfix_phase_methods.md",
        ],
    ),
    (
        "11",
        "production-multi-window",
        "Production multi-window qualification",
        "frame-methods",
        ["tools/replay_150802_pnt_kalman_v4_canary.py"],
    ),
    (
        "12",
        "short-segments-long-glrt",
        "Short segments versus long GLRT lines",
        "frame-methods",
        [
            "reports/2026_09_23_long_dwell_multiscale_phase.md",
            "reports/2026_09_23_longarc_phase_reliability.md",
        ],
    ),
    (
        "13",
        "scanner-retune-bounded",
        "Scanner retune-bounded tracking",
        "frame-methods",
        [
            "tools/report_adaptive_dual_rx_phase.py",
            "reports/2026_09_23_adaptive_retune_phase_audit.md",
        ],
    ),
    (
        "14",
        "semi-coherent-pooling",
        "Semi-coherent pooling",
        "frame-methods",
        [
            "tools/report_470384_semicoherent_recovery.py",
            "reports/2026_08_23_470384_semicoherent_recovery.md",
        ],
    ),
    (
        "15",
        "capture-reset-mechanism",
        "Capture/reset mechanism",
        "frame-methods",
        [
            "reports/2026_09_25_glrt_timestamp_contamination.md",
            "reports/2026_09_23_adaptive_retune_phase_audit.md",
        ],
    ),
    (
        "16",
        "robust-jump-phase-gated",
        "Robust jump and phase-gated filters",
        "frame-methods",
        [
            "reports/2026_08_25_five_dwell_pilot_filter_prototypes.md",
            "reports/2026_09_24_consolidated_phase_methods.md",
        ],
    ),
    (
        "17",
        "v3-phase-safe",
        "V3 phase-safe tracking",
        "frame-methods",
        [
            "tools/replay_150802_pnt_kalman_v4_canary.py",
            "reports/2026_08_25_pnt_kalman_v3_comprehensive_review.md",
        ],
    ),
    (
        "18",
        "v4-seed-control",
        "V4 seed/control correction",
        "frame-methods",
        [
            "tools/replay_150802_pnt_kalman_v4_canary.py",
            "reports/2026_08_25_150802_pnt_kalman_v4_experimental.md",
            "reports/2026_08_25_pnt_kalman_v4_correction_plan.md",
        ],
    ),
    (
        "19",
        "pss-sss-carrier-phase",
        "PSS/SSS carrier phase",
        "sync-spectral",
        [
            "reports/2026_08_25_multi_dwell_pss_sss_doppler.md",
            "reports/2026_09_25_pss_precision_lock.md",
            "reports/2026_09_25_pss_wideband_fractional_alignment.md",
        ],
    ),
    (
        "20",
        "pss-timing-weighting",
        "PSS timing phase / weighting",
        "sync-spectral",
        [
            "reports/2026_09_25_dual_rx_10msps_pss_glrt.md",
            "reports/2026_09_25_five_glrt_tracks_pss_reconstruction.md",
        ],
    ),
    (
        "21",
        "dual-rx-pilot-double-difference",
        "Dual-RX pilot double difference",
        "dual-rx",
        [
            "reports/2026_09_21_matched_pilot_double_difference_noise_control.md",
            "reports/2026_09_21_scan_hop_28d_matched_pilot_dd.md",
        ],
    ),
    (
        "22",
        "double-difference-window-common-frame",
        "Double-difference window/common-frame tests",
        "dual-rx",
        [
            "reports/2026_09_21_scan_hop_28d_simultaneous_dd_cohort.md",
            "reports/2026_09_23_long_dwell_multiscale_protocol.md",
        ],
    ),
    (
        "23",
        "response-normalized-disjoint-band",
        "Response-normalized disjoint-band phase",
        "dual-rx",
        [
            "src/leo/analysis/starlink/relative_phase.py",
            "reports/2026_09_24_late_dual_rx_track_phase.md",
            "reports/2026_09_21_full_bandwidth_rx_alignment.md",
        ],
    ),
    (
        "24",
        "direct-dual-rx-iq",
        "Direct dual-RX IQ",
        "dual-rx",
        [
            "reports/2026_09_21_scan_hop_28d_raw_iq_phase_audit.md",
            "reports/2026_09_24_dual_capture_phase_random_holdout.md",
        ],
    ),
    (
        "25",
        "aggregate-per-bin-fft",
        "Aggregate and per-bin FFT",
        "sync-spectral",
        [
            "reports/2026_09_21_glrt_guided_broadband_phase.md",
            "reports/2026_09_23_matched_bandwidth_phase_results.md",
        ],
    ),
    (
        "26",
        "bandwidth",
        "Bandwidth",
        "sync-spectral",
        [
            "reports/2026_09_21_full_bandwidth_rx_alignment.md",
            "reports/2026_09_23_matched_bandwidth_phase_results.md",
        ],
    ),
    (
        "27",
        "absolute-phase-track",
        "Absolute phase across a track",
        "cross-dwell",
        [
            "reports/2026_09_21_recent8h_long_track_phase.md",
            "reports/2026_09_24_late_dual_rx_track_phase.md",
        ],
    ),
    (
        "28",
        "global-time-boundary-transport",
        "Global-time adjacent-boundary transport",
        "cross-dwell",
        [
            "reports/2026_09_25_adjacent_dwell_phase_transport/REPORT.md",
            "reports/2026_09_23_longarc_phase_transport.md",
            "reports/2026_09_23_longarc_timing.md",
        ],
    ),
    (
        "29",
        "cross-track-replication",
        "Cross-track replication",
        "cross-dwell",
        [
            "reports/2026_09_21_scan_hop_6ad_long_track_phase.md",
            "reports/2026_09_22_multi_dwell_shared_track_phase.md",
        ],
    ),
    (
        "30",
        "phase-assisted-association",
        "Phase-assisted association",
        "cross-dwell",
        [
            "reports/2026_09_24_phase_satellite_association.md",
            "reports/2026_09_25_phase_assisted_satellite_association/REPORT.md",
        ],
    ),
]


def main() -> None:
    methods = []
    for number, slug, name, owner, references in METHODS:
        missing = [path for path in references if not (HERE.parents[1] / path).exists()]
        methods.append(
            {
                "method_id": f"{number}-{slug}",
                "ledger_row": int(number),
                "name": name,
                "owner_output": owner,
                "historical_report_refs": references,
                "historical_ref_availability": "missing_in_this_worktree" if missing else "present",
                "missing_historical_refs": missing,
                "required": True,
                "result_schema": "result-schema.json#scan-phase-replay-method-result/v1",
                "allowed_terminal_outcomes": [
                    "completed",
                    "failed",
                    "not_applicable",
                    "incomplete",
                ],
                "execution_binding": {"status": "pending", "result_path": None},
            }
        )
    document = {
        "schema": "scan-phase-replay-method-registry/v1",
        "recording_id": "scan-fw-32a202b6e55630ec",
        "selection": {
            "path": "selection.json",
            "sha256": "sha256:b73c0d5322a6a70c6ee851ee80ad99ef62ca13b190ae4bdeb35ce95ce2030115",
        },
        "primary_local_mode_policy": {
            "selection": (
                "highest corrected fractional exact-control margin per receiver/probe; "
                "original acquisition rank breaks exact ties"
            ),
            "additional_modes": (
                "retain every admitted mode for explicit multimode and two-signal analyses"
            ),
            "prohibition": "no phase-selected branch stitching",
            "authority": "EXECUTION.md frozen before phase read",
        },
        "counts": {"ledger_rows": len(methods), "required": len(methods)},
        "methods": methods,
    }
    (HERE / "method-registry.json").write_text(json.dumps(document, indent=2) + "\n")


if __name__ == "__main__":
    main()
