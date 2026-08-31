#!/usr/bin/env python3
"""Summarize and fit the coherent episode in this capture's PSS replay."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

CAPTURE_DIR = Path(__file__).resolve().parents[1]
REPLAY_PATH = CAPTURE_DIR / "pss-frame-timing-replay.json"
SUMMARY_PATH = CAPTURE_DIR / "pss-qualified-episode-fit.json"
FIGURE_PATH = CAPTURE_DIR / "pss-qualified-episode-fit.png"
LOCAL_PEAK_TO_MEDIAN_MIN = 5.0
LNB_LO_HZ = 9_750_000_000.0


def _qualified_block_points(target: dict) -> list[dict]:
    sample_rate_hz = float(target["sample_rate_hz"])
    points: list[dict] = []
    for block in target["blocks"]:
        result = block["result"]
        if result["status"] != "complete":
            continue
        for candidate in result["candidates"]:
            if not candidate["qualified"]:
                continue
            candidate_index = candidate["candidate_index"]
            strong_windows = [
                window
                for window in result["windows"]
                if window["candidate_index"] == candidate_index
                and window["peak_to_local_median"] >= LOCAL_PEAK_TO_MEDIAN_MIN
            ]
            if not strong_windows:
                continue
            midpoint_sample = result["global_device_sample_start"] + result["sample_count"] / 2
            points.append(
                {
                    "block_index": block["block_index"],
                    "device_time_s": midpoint_sample / sample_rate_hz,
                    "frame_phase_samples": float(
                        np.median([window["frame_phase_samples"] for window in strong_windows])
                    ),
                    "frame_phase_us": float(
                        np.median([window["frame_phase_samples"] for window in strong_windows])
                        / sample_rate_hz
                        * 1e6
                    ),
                    "strong_window_count": len(strong_windows),
                    "window_count": sum(
                        window["candidate_index"] == candidate_index for window in result["windows"]
                    ),
                    "robust_z": candidate["robust_z"],
                    "folded_peak_to_median": candidate["peak_to_median"],
                }
            )
    return points


def _fit(points: list[dict], degree: int, carrier_hz: float) -> dict:
    x = np.asarray([point["device_time_s"] for point in points], dtype=float)
    y = np.asarray([point["frame_phase_us"] for point in points], dtype=float)
    origin_s = float(np.mean(x))
    centered = x - origin_s
    coefficients = np.polyfit(centered, y, degree)
    prediction = np.polyval(coefficients, centered)
    residual = y - prediction
    slope_at_origin_us_per_s = float(coefficients[-2])
    result = {
        "degree": degree,
        "time_origin_device_s": origin_s,
        "coefficients_descending_us": coefficients.tolist(),
        "rms_residual_us": float(np.sqrt(np.mean(residual**2))),
        "max_abs_residual_us": float(np.max(np.abs(residual))),
        "slope_at_origin_us_per_s": slope_at_origin_us_per_s,
        "doppler_equivalent_at_origin_hz": float(-carrier_hz * slope_at_origin_us_per_s * 1e-6),
        "prediction_us": prediction.tolist(),
        "residual_us": residual.tolist(),
    }
    if degree == 2:
        result["timing_curvature_us_per_s2"] = float(2 * coefficients[0])
        result["doppler_rate_equivalent_hz_per_s"] = float(-carrier_hz * 2 * coefficients[0] * 1e-6)
    return result


def _render(points: list[dict], fits: list[dict]) -> None:
    x = np.asarray([point["device_time_s"] for point in points], dtype=float)
    y = np.asarray([point["frame_phase_us"] for point in points], dtype=float)
    colors = {1: "#0072B2", 2: "#D55E00"}
    labels = {1: "linear", 2: "quadratic"}

    plt.style.use("seaborn-v0_8-whitegrid")
    figure, (axis_fit, axis_residual) = plt.subplots(
        2,
        1,
        figsize=(10.8, 7.4),
        sharex=True,
        gridspec_kw={"height_ratios": [2.1, 1]},
        constrained_layout=True,
    )
    axis_fit.scatter(x, y, color="#222222", s=48, zorder=4, label="qualified block median")
    dense_x = np.linspace(float(np.min(x)), float(np.max(x)), 500)
    for fit in fits:
        degree = fit["degree"]
        dense_prediction = np.polyval(
            fit["coefficients_descending_us"], dense_x - fit["time_origin_device_s"]
        )
        label = f"{labels[degree]} fit (RMS {fit['rms_residual_us']:.3f} us)"
        axis_fit.plot(dense_x, dense_prediction, color=colors[degree], linewidth=2.2, label=label)
        axis_residual.plot(
            x,
            fit["residual_us"],
            marker="o",
            color=colors[degree],
            linewidth=1.6,
            label=labels[degree],
        )

    axis_fit.set_title("2.5 MS/s RX1: coherent PSS frame-timing episode")
    axis_fit.set_ylabel("Median PSS frame phase (us)")
    axis_fit.legend(loc="upper left")
    axis_fit.text(
        0.99,
        0.03,
        f"local peak/median >= {LOCAL_PEAK_TO_MEDIAN_MIN:g}; one median per qualified block",
        transform=axis_fit.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="#444444",
    )
    axis_residual.axhline(0, color="#444444", linewidth=1)
    axis_residual.set_xlabel("Device time since stream start (s)")
    axis_residual.set_ylabel("Residual (us)")
    axis_residual.legend(loc="best", ncol=2)
    figure.savefig(FIGURE_PATH, dpi=180)
    plt.close(figure)


def main() -> None:
    replay = json.loads(REPLAY_PATH.read_text())
    rf_reference_hz = replay["channel_reference_hz"] + LNB_LO_HZ
    targets = []
    for target in replay["targets"]:
        points = _qualified_block_points(target)
        targets.append(
            {
                "stream_id": target["stream_id"],
                "receiver_id": target["receiver_id"],
                "sample_rate_hz": target["sample_rate_hz"],
                "summary": target["summary"],
                "qualified_block_points": points,
            }
        )

    coherent_target = next(
        target
        for target in targets
        if target["sample_rate_hz"] == 2_500_000 and target["receiver_id"] == 1
    )
    points = coherent_target["qualified_block_points"]
    fits = [_fit(points, degree, rf_reference_hz) for degree in (1, 2)]
    output = {
        "analysis_kind": "pss_qualified_episode_fit",
        "capture_id": replay["capture_id"],
        "source_replay": REPLAY_PATH.name,
        "channel_reference_hz": replay["channel_reference_hz"],
        "lnb_lo_hz": LNB_LO_HZ,
        "conditional_rf_reference_hz": rf_reference_hz,
        "local_peak_to_median_min": LOCAL_PEAK_TO_MEDIAN_MIN,
        "coordinate_semantics": {
            "device_time_s": (
                "Per-stream device sample coordinate divided by that stream's sample rate."
            ),
            "cross_stream_phase": "Not compared: the manifest declares phase_coherent=false.",
            "doppler_equivalent": (
                "Derived from timing slope using -carrier_hz * d(delay)/dt; sign remains "
                "analyzer-convention dependent."
            ),
        },
        "targets": targets,
        "coherent_episode": {
            "stream_id": coherent_target["stream_id"],
            "receiver_id": coherent_target["receiver_id"],
            "sample_rate_hz": coherent_target["sample_rate_hz"],
            "point_count": len(points),
            "device_time_start_s": min(point["device_time_s"] for point in points),
            "device_time_stop_s": max(point["device_time_s"] for point in points),
            "fits": fits,
        },
    }
    SUMMARY_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    _render(points, fits)


if __name__ == "__main__":
    main()
