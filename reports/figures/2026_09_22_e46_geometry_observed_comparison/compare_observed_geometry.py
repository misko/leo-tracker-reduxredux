#!/usr/bin/env python3
"""Compare the conditional e46 geometry prediction with published phase results."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RATE_HZ = 2_500_000.0
C_M_S = 299_792_458.0
NOMINAL_BASELINE_M = 0.09736481776669303


def wrap_deg(value: np.ndarray | float) -> np.ndarray:
    return (np.asarray(value) + 180.0) % 360.0 - 180.0


def circular_offset_and_residual(observed_deg: np.ndarray, predicted_deg: np.ndarray):
    delta = np.deg2rad(observed_deg - predicted_deg)
    offset = np.angle(np.exp(1j * delta).sum())
    residual = np.rad2deg(np.angle(np.exp(1j * (delta - offset))))
    resultant = float(abs(np.exp(1j * delta).mean()))
    rms = float(np.sqrt(np.mean(residual**2)))
    return float(np.rad2deg(offset)), residual, resultant, rms


def circular_rms_with_rate(time_s: np.ndarray, phase_deg: np.ndarray, rate_deg_s: float) -> float:
    detrended = np.deg2rad(phase_deg - rate_deg_s * time_s)
    offset = np.angle(np.exp(1j * detrended).sum())
    residual = np.angle(np.exp(1j * (detrended - offset)))
    return float(np.rad2deg(np.sqrt(np.mean(residual**2))))


def main() -> None:
    output = Path(__file__).resolve().parent
    reports = output.parents[1]
    observed_path = reports / "figures/2026_09_22_multi_dwell_track_phase/multi-dwell-results.json"
    geometry_path = reports / "figures/2026_09_22_e46_geometry_phase/geometry-phase-by-dwell.csv"
    observed = json.loads(observed_path.read_text())
    geometry_rows = {
        int(row["visit_index"]): row
        for row in csv.DictReader(geometry_path.open())
        if int(row["candidate"]) == 59925
    }

    rows = []
    for visit in observed["visits"]:
        visit_index = int(visit["visit_index"])
        geometry = geometry_rows[visit_index]
        model = visit["model"]
        edge = visit["edge_pair"]
        edge_delta_s = (edge["center_sample"] - model["reference_sample"]) / RATE_HZ
        broadband_cfo_at_edge = (
            model["relative_cfo_hz"] + model["relative_cfo_rate_hz_s"] * edge_delta_s
        )
        geometry_rate_deg_s = float(geometry["nominal_phase_rate_deg_s"])
        window_time_s = np.asarray([row["center_time_ms"] for row in visit["windows"]]) / 1000.0
        window_phase_deg = np.asarray([row["phase_deg"] for row in visit["windows"]])
        constant_rms = circular_rms_with_rate(window_time_s, window_phase_deg, 0.0)
        geometry_rms = circular_rms_with_rate(
            window_time_s, window_phase_deg, geometry_rate_deg_s
        )
        summary = next(
            row for row in observed["summary"] if int(row["visit_index"]) == visit_index
        )
        rows.append(
            {
                "visit_index": visit_index,
                "track_elapsed_s": float(visit["track_elapsed_s"]),
                "geometry_phase_deg": float(geometry["nominal_geometric_phase_deg"]),
                "geometry_delay_ns": float(
                    NOMINAL_BASELINE_M * float(geometry["east_direction_cosine"]) / C_M_S * 1e9
                ),
                "geometry_delay_samples": float(
                    NOMINAL_BASELINE_M
                    * float(geometry["east_direction_cosine"])
                    / C_M_S
                    * RATE_HZ
                ),
                "geometry_phase_rate_deg_s": geometry_rate_deg_s,
                "geometry_equivalent_frequency_hz": geometry_rate_deg_s / 360.0,
                "geometry_change_per_120ms_deg": float(
                    geometry["nominal_change_per_120ms_deg"]
                ),
                "edge_pilot_phase_deg": float(summary["edge_pilot_phase_deg"]),
                "edge_pilot_phase_se_deg": float(summary["edge_pilot_phase_se_deg"]),
                "broadband_phase_deg": float(summary["broadband_intercept_phase_deg"]),
                "broadband_phase_se_deg": float(summary["broadband_intercept_phase_se_deg"]),
                "edge_frequency_se_hz": float(edge["relative_frequency_standard_error_hz"]),
                "broadband_minus_edge_frequency_hz": float(
                    broadband_cfo_at_edge - edge["relative_frequency_hz"]
                ),
                "rolling_constant_phase_rms_deg": constant_rms,
                "rolling_geometry_rate_rms_deg": geometry_rms,
                "rolling_geometry_rms_improvement_deg": constant_rms - geometry_rms,
                "rolling_median_coherence": float(summary["median_coherence"]),
                "heldout_phase_valid": bool(
                    summary["frequency_held_out_tracked_coherence"]
                    > summary["frequency_held_out_wrong_time_coherence"]
                ),
            }
        )

    fields = list(rows[0])
    with (output / "observed-vs-geometry-by-dwell.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    elapsed = np.asarray([row["track_elapsed_s"] for row in rows])
    geometry_phase = np.asarray([row["geometry_phase_deg"] for row in rows])
    edge_phase = np.asarray([row["edge_pilot_phase_deg"] for row in rows])
    broadband_phase = np.asarray([row["broadband_phase_deg"] for row in rows])
    edge_offset, edge_residual, edge_resultant, edge_rms = circular_offset_and_residual(
        edge_phase, geometry_phase
    )
    broadband_offset, broadband_residual, broadband_resultant, broadband_rms = (
        circular_offset_and_residual(broadband_phase, geometry_phase)
    )
    qualified = np.asarray([row["heldout_phase_valid"] for row in rows], dtype=bool)
    qualified_offset, qualified_residual, qualified_resultant, qualified_rms = (
        circular_offset_and_residual(broadband_phase[qualified], geometry_phase[qualified])
    )

    geometry_frequency = np.asarray([row["geometry_equivalent_frequency_hz"] for row in rows])
    estimator_disagreement = np.abs(
        [row["broadband_minus_edge_frequency_hz"] for row in rows]
    )
    edge_frequency_se = np.asarray([row["edge_frequency_se_hz"] for row in rows])
    constant_rms = np.asarray([row["rolling_constant_phase_rms_deg"] for row in rows])
    geometry_rms = np.asarray([row["rolling_geometry_rate_rms_deg"] for row in rows])
    improvement = constant_rms - geometry_rms

    result = {
        "schema": "org.leo.report.e46-observed-geometry-comparison/v1",
        "session_id": observed["session_id"],
        "candidate": 59925,
        "nominal_baseline_m": NOMINAL_BASELINE_M,
        "phase_comparison": {
            "edge_pilot": {
                "best_global_offset_deg": edge_offset,
                "circular_residual_rms_deg": edge_rms,
                "residual_resultant": edge_resultant,
            },
            "broadband_intercept_all": {
                "best_global_offset_deg": broadband_offset,
                "circular_residual_rms_deg": broadband_rms,
                "residual_resultant": broadband_resultant,
            },
            "broadband_intercept_heldout_valid": {
                "count": int(np.count_nonzero(qualified)),
                "best_global_offset_deg": qualified_offset,
                "circular_residual_rms_deg": qualified_rms,
                "residual_resultant": qualified_resultant,
            },
        },
        "frequency_scale": {
            "geometry_range_hz": [float(geometry_frequency.min()), float(geometry_frequency.max())],
            "edge_conditional_se_range_hz": [
                float(edge_frequency_se.min()), float(edge_frequency_se.max())
            ],
            "edge_conditional_se_median_hz": float(np.median(edge_frequency_se)),
            "edge_se_over_geometry_median": float(np.median(edge_frequency_se / geometry_frequency)),
            "broadband_edge_abs_disagreement_range_hz": [
                float(estimator_disagreement.min()), float(estimator_disagreement.max())
            ],
            "broadband_edge_abs_disagreement_median_hz": float(
                np.median(estimator_disagreement)
            ),
        },
        "delay_scale": {
            "geometry_delay_range_ns": [
                float(min(row["geometry_delay_ns"] for row in rows)),
                float(max(row["geometry_delay_ns"] for row in rows)),
            ],
            "geometry_delay_change_samples": float(
                max(row["geometry_delay_samples"] for row in rows)
                - min(row["geometry_delay_samples"] for row in rows)
            ),
            "full_baseline_delay_samples": float(NOMINAL_BASELINE_M / C_M_S * RATE_HZ),
        },
        "within_dwell": {
            "constant_model_rms_range_deg": [float(constant_rms.min()), float(constant_rms.max())],
            "geometry_model_rms_range_deg": [float(geometry_rms.min()), float(geometry_rms.max())],
            "geometry_rms_improvement_median_deg": float(np.median(improvement)),
            "geometry_rms_improvement_range_deg": [float(improvement.min()), float(improvement.max())],
        },
        "interpretation": (
            "The predicted geometric rate is below real frequency uncertainty and residual model "
            "disagreement; retune/path phase prevents one global phase-offset fit across dwells."
        ),
    }
    (output / "observed-vs-geometry-summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )

    fig, axes = plt.subplots(2, 2, figsize=(13, 9.5), constrained_layout=True)
    ax = axes[0, 0]
    fine_t = np.linspace(elapsed.min(), elapsed.max(), 1000)
    fine_phase = np.interp(fine_t, elapsed, geometry_phase)
    wrapped = wrap_deg(fine_phase)
    wrapped[1:][np.abs(np.diff(wrapped)) > 180] = np.nan
    ax.plot(fine_t, wrapped, color="#111827", lw=2, label="geometry: 59925, 97.36 mm")
    ax.errorbar(
        elapsed,
        wrap_deg(edge_phase - edge_offset),
        yerr=[row["edge_pilot_phase_se_deg"] for row in rows],
        fmt="^",
        color="#dc2626",
        capsize=2,
        label="edge pilot − best global offset",
    )
    ax.errorbar(
        elapsed,
        wrap_deg(broadband_phase - broadband_offset),
        yerr=[row["broadband_phase_se_deg"] for row in rows],
        fmt="s",
        color="#2563eb",
        capsize=2,
        label="broadband − best global offset",
    )
    ax.set(title="A single phase offset does not align observed dwells", ylabel="wrapped phase (degrees)")
    ax.set_ylim(-190, 190)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, frameon=False)

    ax = axes[0, 1]
    ax.semilogy(elapsed, geometry_frequency, "o-", color="#111827", label="predicted geometry")
    ax.semilogy(elapsed, edge_frequency_se, "s-", color="#2563eb", label="edge CFO conditional SE")
    ax.semilogy(
        elapsed,
        np.maximum(estimator_disagreement, 1e-3),
        "^-",
        color="#f97316",
        label="|broadband CFO − edge CFO|",
    )
    ax.set(title="Geometry is below the real frequency-error scale", ylabel="frequency magnitude (Hz)")
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8, frameon=False)

    ax = axes[1, 0]
    ax.plot(elapsed, constant_rms, "o-", color="#64748b", label="constant phase + fitted intercept")
    ax.plot(elapsed, geometry_rms, "s-", color="#0f766e", label="geometry rate + fitted intercept")
    ax.set(
        title="Geometry cannot explain the rolling phase trajectories",
        xlabel="elapsed track time (s)",
        ylabel="circular residual RMS (degrees)",
    )
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, frameon=False)

    ax = axes[1, 1]
    ax.bar(elapsed, improvement, width=1.7, color=np.where(improvement >= 0, "#0f766e", "#dc2626"))
    ax.axhline(0, color="#111827", lw=1)
    ax.set(
        title="Adding the orbital rate changes RMS by less than 0.5°",
        xlabel="elapsed track time (s)",
        ylabel="constant RMS − geometry RMS (degrees)",
    )
    ax.grid(alpha=0.25, axis="y")

    fig.suptitle(
        "Observed RX1−RX0 phase versus conditional LT3D-001A geometry\n"
        "same 12 dwells; candidate 59925; positive nominal eastward baseline",
        fontsize=14,
    )
    fig.savefig(output / "observed-vs-geometry.png", dpi=180)


if __name__ == "__main__":
    main()
