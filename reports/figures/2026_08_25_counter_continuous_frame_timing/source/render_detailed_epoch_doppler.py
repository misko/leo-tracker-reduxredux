#!/usr/bin/env python3
"""Render detailed Matplotlib timing and Doppler-equivalent curvature plots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SAMPLE_RATE_HZ = 2_500_000.0
FRAME_RATE_HZ = 750.0
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / FRAME_RATE_HZ
PROBE_SAMPLES = round(0.020 * SAMPLE_RATE_HZ)
INTERVAL_START_S = 37.575
INTERVAL_STOP_S = 51.4
TRAJECTORY_ID = "sha256:92955a7dc86076490a7150b7f233ef64519fb7c0999bba1e62d94dfa531b5d8c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = [value for value in candidate["scores"] if value["method"] == "glrt64"]
    if len(scores) != 1:
        raise ValueError("candidate must contain exactly one GLRT64 score")
    return scores[0]


def trajectory_cfo(trajectory: dict[str, Any], time_s: float) -> float:
    slope, at_reference = (float(value) for value in trajectory["absolute_coefficients_hz"])
    return at_reference + slope * (time_s - float(trajectory["reference_time_s"]))


def match_key(
    value: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> tuple[float, float, int, int, int]:
    detection, candidate, score = value
    return (
        float(score["margin"]),
        float(score["exact_score"]),
        -int(candidate["rank"]),
        -int(detection["sample_start"]),
        -int(candidate["local_epoch_sample"]),
    )


def select_detections(
    scan: dict[str, Any], trajectory: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    interval_start = round(INTERVAL_START_S * SAMPLE_RATE_HZ)
    interval_stop = round(INTERVAL_STOP_S * SAMPLE_RATE_HZ)
    matches: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for detection in scan["detections"]:
        if detection["status"] != "complete":
            continue
        sample_start = int(detection["sample_start"])
        if sample_start < interval_start or sample_start + PROBE_SAMPLES > interval_stop:
            continue
        target = trajectory_cfo(trajectory, float(detection["time_s"]))
        for candidate in detection["candidates"]:
            score = glrt_score(candidate)
            if (
                int(candidate["rank"]) <= 2
                and 0 <= int(candidate["local_epoch_sample"]) < math.ceil(FRAME_PERIOD_SAMPLES)
                and float(score["margin"]) >= 0.05
                and float(score["exact_score"]) >= 0.02
                and abs(float(score["tracking_cfo_hz"]) - target) <= 2_000.0
            ):
                matches.append((detection, candidate, score))

    by_detection: dict[int, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    for value in matches:
        sample_start = int(value[0]["sample_start"])
        current = by_detection.get(sample_start)
        if current is None or match_key(value) > match_key(current):
            by_detection[sample_start] = value

    selected = []
    for detection, candidate, score in sorted(
        by_detection.values(), key=lambda value: int(value[0]["sample_start"])
    ):
        selected.append(
            {
                "probe_time_s": float(detection["time_s"]),
                "detection_sample_start": int(detection["sample_start"]),
                "candidate_rank": int(candidate["rank"]),
                "local_epoch_sample": int(candidate["local_epoch_sample"]),
                "absolute_epoch_sample": int(detection["sample_start"])
                + int(candidate["local_epoch_sample"]),
                "tracking_cfo_hz": float(score["tracking_cfo_hz"]),
                "exact_score": float(score["exact_score"]),
                "control_score": float(score["control_score"]),
                "margin": float(score["margin"]),
            }
        )
    return selected, len(matches)


def epoch_residual(epoch_sample: int, reference_epoch: int) -> float:
    frame_index = round((epoch_sample - reference_epoch) / FRAME_PERIOD_SAMPLES)
    expected = reference_epoch + frame_index * FRAME_PERIOD_SAMPLES
    return float(epoch_sample - expected)


def quadratic_fit(times: np.ndarray, values: np.ndarray) -> dict[str, Any]:
    center = float(np.mean(times))
    x = times - center
    coefficients = np.polyfit(x, values, 2)
    fitted = np.polyval(coefficients, x)
    residuals = values - fitted
    return {
        "center_time_s": center,
        "coefficients_samples": [float(value) for value in coefficients],
        "second_derivative_samples_s2": float(2.0 * coefficients[0]),
        "fit_rms_samples": float(np.sqrt(np.mean(np.square(residuals)))),
        "fit_maximum_absolute_residual_samples": float(np.max(np.abs(residuals))),
        "fitted_samples": fitted,
        "residual_samples": residuals,
    }


def local_curvature(
    times: np.ndarray,
    epoch_offsets: np.ndarray,
    cfo_hz: np.ndarray,
    *,
    rf_hz: float,
    window_s: float,
    step_s: float = 0.25,
) -> list[dict[str, float]]:
    centers = np.arange(
        times[0] + window_s / 2.0,
        times[-1] - window_s / 2.0 + 1e-9,
        step_s,
    )
    output = []
    for center in centers:
        selected = np.abs(times - center) <= window_s / 2.0 + 1e-9
        x = times[selected] - center
        timing_coefficients = np.polyfit(x, epoch_offsets[selected], 2)
        cfo_coefficients = np.polyfit(x, cfo_hz[selected], 1)
        repository_signed_rate = rf_hz / SAMPLE_RATE_HZ * 2.0 * float(timing_coefficients[0])
        output.append(
            {
                "center_time_s": float(center),
                "window_s": float(window_s),
                "point_count": int(np.count_nonzero(selected)),
                "timing_repository_signed_rate_hz_s": repository_signed_rate,
                "timing_rate_magnitude_hz_s": abs(repository_signed_rate),
                "direct_cfo_rate_hz_s": float(cfo_coefficients[0]),
                "direct_cfo_rate_magnitude_hz_s": abs(float(cfo_coefficients[0])),
            }
        )
    return output


def summarize_local_curvature(rows: list[dict[str, float]]) -> dict[str, float | int]:
    timing = np.asarray([row["timing_repository_signed_rate_hz_s"] for row in rows])
    direct = np.asarray([row["direct_cfo_rate_hz_s"] for row in rows])
    return {
        "count": int(timing.size),
        "timing_minimum_hz_s": float(np.min(timing)),
        "timing_median_hz_s": float(np.median(timing)),
        "timing_maximum_hz_s": float(np.max(timing)),
        "direct_minimum_hz_s": float(np.min(direct)),
        "direct_median_hz_s": float(np.median(direct)),
        "direct_maximum_hz_s": float(np.max(direct)),
        "timing_minus_direct_rms_hz_s": float(np.sqrt(np.mean(np.square(timing - direct)))),
        "timing_direct_correlation": float(np.corrcoef(timing, direct)[0, 1]),
    }


def render_full(
    output: Path,
    *,
    times: np.ndarray,
    epoch_offsets: np.ndarray,
    anchor_times: np.ndarray,
    anchor_offsets: np.ndarray,
    all_fit: dict[str, Any],
    anchor_fit: dict[str, Any],
    local_four: list[dict[str, float]],
    local_five: list[dict[str, float]],
    local_six: list[dict[str, float]],
    refill_times: np.ndarray,
    persisted_rate_hz_s: float,
) -> None:
    fitted = np.asarray(all_fit["fitted_samples"])
    residuals = np.asarray(all_fit["residual_samples"])
    four_t = np.asarray([row["center_time_s"] for row in local_four])
    four_rate = np.asarray([row["timing_repository_signed_rate_hz_s"] for row in local_four])
    five_t = np.asarray([row["center_time_s"] for row in local_five])
    five_timing = np.asarray([row["timing_repository_signed_rate_hz_s"] for row in local_five])
    six_t = np.asarray([row["center_time_s"] for row in local_six])
    six_timing = np.asarray([row["timing_repository_signed_rate_hz_s"] for row in local_six])
    six_direct = np.asarray([row["direct_cfo_rate_hz_s"] for row in local_six])
    all_rate = float(all_fit["doppler_equivalent_repository_signed_hz_s"])
    anchor_rate = float(anchor_fit["doppler_equivalent_repository_signed_hz_s"])

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 8,
            "figure.titlesize": 13,
        }
    )
    figure, axes = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        dpi=150,
        sharex=True,
        constrained_layout=False,
        gridspec_kw={"height_ratios": (1.7, 1.0, 1.25)},
    )
    figure.subplots_adjust(
        left=0.075,
        right=0.94,
        bottom=0.09,
        top=0.90,
        hspace=0.28,
    )
    figure.suptitle(
        "Detailed frame-epoch drift and Doppler-equivalent curvature\n"
        "550 trajectory-conditioned GLRT detections at nominal 25 ms cadence · candidate-only"
    )

    ax = axes[0]
    ax.plot(
        times,
        epoch_offsets,
        color="#7561c9",
        linewidth=0.65,
        alpha=0.65,
        label="all selected GLRT epoch detections",
    )
    ax.scatter(times, epoch_offsets, s=7, color="#7561c9", alpha=0.45, linewidths=0)
    ax.plot(
        times,
        fitted,
        color="#21145f",
        linewidth=1.8,
        label="global quadratic timing fit",
    )
    ax.scatter(
        anchor_times,
        anchor_offsets,
        s=30,
        color="#d97706",
        edgecolors="white",
        linewidths=0.5,
        zorder=4,
        label="28 selected anchors (initial + 27 refresh)",
    )
    ax.axhline(0.0, color="#202020", linewidth=0.8)
    ax.set_ylabel("Observed − fixed lattice (samples)")
    secondary = ax.secondary_yaxis(
        "right",
        functions=(
            lambda samples: samples * 1_000_000.0 / SAMPLE_RATE_HZ,
            lambda microseconds: microseconds * SAMPLE_RATE_HZ / 1_000_000.0,
        ),
    )
    secondary.set_ylabel("Equivalent timing offset (µs)")
    ax.set_title(
        "The original purple curve resolved into its 25 ms measurements "
        "(line segments are visual interpolation)"
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=2)

    ax = axes[1]
    ax.plot(times, residuals, color="#7561c9", linewidth=0.55, alpha=0.60)
    ax.scatter(times, residuals, s=7, color="#7561c9", alpha=0.48, linewidths=0)
    anchor_center = float(all_fit["center_time_s"])
    anchor_coefficients = np.asarray(all_fit["coefficients_samples"])
    anchor_residuals = anchor_offsets - np.polyval(
        anchor_coefficients, anchor_times - anchor_center
    )
    ax.scatter(
        anchor_times,
        anchor_residuals,
        s=28,
        color="#d97706",
        edgecolors="white",
        linewidths=0.45,
        zorder=4,
        label="selected-anchor residual on same fit",
    )
    rug_y = float(np.min(residuals)) - 0.08
    ax.scatter(
        refill_times,
        np.full(refill_times.shape, rug_y),
        marker="|",
        s=18,
        color="#8b8b8b",
        alpha=0.42,
        linewidths=0.65,
        label="132 counter-contiguous refills (rug)",
    )
    ax.axhline(0.0, color="#202020", linewidth=0.8)
    ax.set_ylabel("Residual to quadratic (samples)")
    ax.set_title(
        f"Global quadratic residual: {all_fit['fit_rms_samples']:.3f} sample RMS, "
        f"{all_fit['fit_maximum_absolute_residual_samples']:.3f} sample maximum"
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[2]
    ax.plot(
        four_t,
        four_rate,
        color="#a99be3",
        linewidth=1.1,
        linestyle="--",
        label="timing curvature, 4 s local quadratic",
    )
    ax.plot(
        five_t,
        five_timing,
        color="#7561c9",
        linewidth=1.6,
        label="timing curvature, 5 s local quadratic",
    )
    ax.plot(
        six_t,
        six_timing,
        color="#5b4bb7",
        marker="o",
        markersize=2.8,
        linewidth=1.5,
        label="timing curvature, 6 s local quadratic",
    )
    ax.plot(
        six_t,
        six_direct,
        color="#444444",
        linewidth=1.3,
        label="direct CFO slope, identical 6 s windows",
    )
    ax.axhline(
        persisted_rate_hz_s,
        color="#111111",
        linewidth=1.0,
        linestyle=":",
        label=f"persisted direct-CFO slope {persisted_rate_hz_s:.1f} Hz/s",
    )
    ax.axhline(
        all_rate,
        color="#5b4bb7",
        linewidth=1.0,
        linestyle=":",
        label=f"all-detection timing curvature {all_rate:.1f} Hz/s",
    )
    ax.set_ylabel("Same-sign RF-scaled timing curvature (Hz/s)")
    ax.set_xlabel("Time from dwell start (s)")
    ax.set_title(
        f"Retrospective local quadratics; anchor-only full-arc {anchor_rate:.1f} Hz/s. "
        f"6 s timing-v-direct RMS difference "
        f"{np.sqrt(np.mean(np.square(six_timing - six_direct))):.1f} Hz/s."
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=2)
    ax.set_xlim(INTERVAL_START_S, INTERVAL_STOP_S)

    figure.text(
        0.5,
        0.014,
        "Window sensitivity is not a confidence interval. Doppler-equivalent frame-clock "
        "curvature is not identified physical Doppler.\n"
        "For observed−nominal epoch, conventional propagation-delay sign is opposite; "
        "clock/LO drift and conditional joint epoch/CFO selection remain confounded.",
        ha="center",
        va="bottom",
        fontsize=7.5,
        color="#333333",
    )

    figure.savefig(output, dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def render_zoom(
    output: Path,
    *,
    times: np.ndarray,
    epoch_offsets: np.ndarray,
    fitted: np.ndarray,
    zoom_start_s: float,
    zoom_stop_s: float,
) -> None:
    selected = (times >= zoom_start_s) & (times <= zoom_stop_s)
    figure, axes = plt.subplots(
        2,
        1,
        figsize=(13, 7),
        dpi=150,
        sharex=True,
        constrained_layout=True,
    )
    figure.suptitle(
        f"Detailed 25 ms epoch detections: {zoom_start_s:.3f}–{zoom_stop_s:.3f} s\n"
        "observed-minus-fixed-lattice convention"
    )
    ax = axes[0]
    ax.plot(times[selected], epoch_offsets[selected], color="#7561c9", linewidth=0.9)
    ax.scatter(
        times[selected],
        epoch_offsets[selected],
        s=22,
        color="#5b4bb7",
        edgecolors="white",
        linewidths=0.4,
        zorder=3,
        label="GLRT epoch detection",
    )
    ax.plot(
        times[selected],
        fitted[selected],
        color="#21145f",
        linewidth=1.6,
        label="global quadratic fit",
    )
    ax.set_ylabel("Epoch residual (samples)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")

    ax = axes[1]
    zoom_residuals = epoch_offsets[selected] - fitted[selected]
    ax.vlines(
        times[selected],
        0.0,
        zoom_residuals,
        color="#a99be3",
        linewidth=0.7,
        alpha=0.75,
    )
    ax.scatter(
        times[selected],
        zoom_residuals,
        s=18,
        color="#5b4bb7",
        edgecolors="white",
        linewidths=0.35,
        zorder=3,
    )
    ax.axhline(0.0, color="#333333", linewidth=0.8)
    ax.set_ylabel("Residual to fit (samples)")
    ax.set_xlabel("Time from dwell start (s)")
    ax.set_title("Integer-sample epochs appear in one-third-sample lattice residual increments")
    ax.grid(True, alpha=0.25)
    ax.set_xlim(zoom_start_s, zoom_stop_s)

    figure.savefig(output, dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--long-root", type=Path, required=True)
    parser.add_argument("--pilot-scan", type=Path, required=True)
    parser.add_argument("--trajectory-bank", type=Path, required=True)
    parser.add_argument("--recording-manifest", type=Path, required=True)
    parser.add_argument("--zoom-start-s", type=float, default=45.5)
    parser.add_argument("--zoom-stop-s", type=float, default=46.5)
    args = parser.parse_args()

    long_evidence_path = args.long_root / "evidence.json"
    long_evidence = load(long_evidence_path)
    declared_hashes = long_evidence["input_sha256"]
    for label, path in (
        ("pilot_scan", args.pilot_scan),
        ("final_trajectory_bank", args.trajectory_bank),
        ("recording_manifest", args.recording_manifest),
    ):
        actual = sha256(path)
        if actual != declared_hashes[label]:
            raise ValueError(f"{label} hash mismatch: {actual} != {declared_hashes[label]}")

    scan = load(args.pilot_scan)
    bank = load(args.trajectory_bank)
    recording = load(args.recording_manifest)
    trajectories = [
        value for value in bank["trajectories"] if value["trajectory_id"] == TRAJECTORY_ID
    ]
    if len(trajectories) != 1:
        raise ValueError("expected exactly one persisted target trajectory")
    trajectory = trajectories[0]
    if trajectory["trajectory_id"] != long_evidence["trajectory"]["trajectory_id"]:
        raise ValueError("long-run trajectory identity mismatch")

    detections, matching_candidate_count = select_detections(scan, trajectory)
    if matching_candidate_count != int(long_evidence["matching_candidate_count"]):
        raise ValueError("matching-candidate count does not reproduce")
    if len(detections) != int(long_evidence["lattice_evidence"]["detection_count"]):
        raise ValueError("selected-detection count does not reproduce")

    anchors = long_evidence["anchors"]
    reference_epoch = int(anchors[0]["absolute_epoch_sample"])
    times = np.asarray([float(row["absolute_epoch_sample"]) / SAMPLE_RATE_HZ for row in detections])
    cfo_hz = np.asarray([float(row["tracking_cfo_hz"]) for row in detections])
    epoch_offsets = np.asarray(
        [epoch_residual(int(row["absolute_epoch_sample"]), reference_epoch) for row in detections]
    )
    anchor_times = np.asarray(
        [float(anchor["absolute_epoch_sample"]) / SAMPLE_RATE_HZ for anchor in anchors]
    )
    anchor_offsets = np.asarray(
        [
            epoch_residual(int(anchor["absolute_epoch_sample"]), reference_epoch)
            for anchor in anchors
        ]
    )

    stream = [value for value in recording["streams"] if value["stream_id"] == "stream-1"]
    if len(stream) != 1:
        raise ValueError("expected exactly one stream-1 recording entry")
    if int(stream[0]["applied_settings"]["sample_rate_hz"]) != int(SAMPLE_RATE_HZ):
        raise ValueError("unexpected recording sample rate")
    lnb_lo_hz = float(recording["capture_plan"]["profile_revision"]["profile"]["lnb_lo_hz"])
    rf_hz = lnb_lo_hz + float(stream[0]["applied_settings"]["center_frequency_hz"])

    all_fit = quadratic_fit(times, epoch_offsets)
    anchor_fit = quadratic_fit(anchor_times, anchor_offsets)
    for fit in (all_fit, anchor_fit):
        fit["doppler_equivalent_repository_signed_hz_s"] = (
            rf_hz / SAMPLE_RATE_HZ * fit["second_derivative_samples_s2"]
        )
        fit["conventional_propagation_signed_hz_s"] = -float(
            fit["doppler_equivalent_repository_signed_hz_s"]
        )

    direct_center = float(np.mean(times))
    direct_coefficients = np.polyfit(times - direct_center, cfo_hz, 1)
    local_four = local_curvature(times, epoch_offsets, cfo_hz, rf_hz=rf_hz, window_s=4.0)
    local_five = local_curvature(times, epoch_offsets, cfo_hz, rf_hz=rf_hz, window_s=5.0)
    local_six = local_curvature(times, epoch_offsets, cfo_hz, rf_hz=rf_hz, window_s=6.0)
    refill_times = (
        np.asarray(long_evidence["refill_audit_boundary_samples"], dtype=float) / SAMPLE_RATE_HZ
    )

    output_evidence = {
        "schema": "org.leo.research.detailed-epoch-doppler-curvature/v1",
        "candidate_only": True,
        "interval": long_evidence["interval"],
        "trajectory_id": TRAJECTORY_ID,
        "reference_epoch_sample": reference_epoch,
        "epoch_offset_convention": "observed_epoch_minus_nearest_fixed_750hz_lattice",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "rf_tuning_center_hz": rf_hz,
        "detection_count": len(detections),
        "matching_candidate_count": matching_candidate_count,
        "refresh_anchor_count": len(anchors),
        "all_detection_quadratic": {
            key: value
            for key, value in all_fit.items()
            if key not in {"fitted_samples", "residual_samples"}
        },
        "anchor_quadratic": {
            key: value
            for key, value in anchor_fit.items()
            if key not in {"fitted_samples", "residual_samples"}
        },
        "direct_cfo_same_detection_linear": {
            "center_time_s": direct_center,
            "coefficients_hz": [float(value) for value in direct_coefficients],
            "rate_hz_s": float(direct_coefficients[0]),
        },
        "persisted_direct_cfo_rate_hz_s": float(trajectory["absolute_coefficients_hz"][0]),
        "local_curvature": {"4s": local_four, "5s": local_five, "6s": local_six},
        "local_curvature_summary": {
            "4s": summarize_local_curvature(local_four),
            "5s": summarize_local_curvature(local_five),
            "6s": summarize_local_curvature(local_six),
        },
        "detections": [
            {
                **row,
                "epoch_residual_samples": float(offset),
                "quadratic_residual_samples": float(residual),
            }
            for row, offset, residual in zip(
                detections,
                epoch_offsets,
                np.asarray(all_fit["residual_samples"]),
                strict=True,
            )
        ],
        "interpretation_limits": [
            "the displayed curve is conditioned on an offline persisted CFO trajectory "
            "and all-Qin GLRT candidate selection",
            "GLRT jointly estimates epoch and CFO, so timing-versus-CFO agreement is "
            "not independent validation",
            "repository-signed RF scaling is chosen for comparison to stored CFO; "
            "conventional propagation-delay sign is opposite",
            "timing curvature contains physical Doppler plus transmitter frame-clock "
            "and receiver sample-clock drift",
            "direct CFO contains physical Doppler plus transmitter carrier, receiver LO, "
            "and LNB drift",
            "4 s, 5 s, and 6 s local windows are exploratory; shorter second-derivative "
            "windows amplify integer-epoch quantization",
            "local estimates are spaced every 0.25 s but their windows overlap heavily; "
            "the effective resolution is the full fit-window duration",
        ],
        "input_sha256": {
            "long_evidence": sha256(long_evidence_path),
            "pilot_scan": sha256(args.pilot_scan),
            "final_trajectory_bank": sha256(args.trajectory_bank),
            "recording_manifest": sha256(args.recording_manifest),
        },
    }

    evidence_path = args.long_root / "epoch-doppler-curvature.json"
    evidence_path.write_text(
        json.dumps(output_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    full_plot = args.long_root / "detailed-epoch-doppler.png"
    zoom_plot = args.long_root / "detailed-epoch-zoom.png"
    render_full(
        full_plot,
        times=times,
        epoch_offsets=epoch_offsets,
        anchor_times=anchor_times,
        anchor_offsets=anchor_offsets,
        all_fit=all_fit,
        anchor_fit=anchor_fit,
        local_four=local_four,
        local_five=local_five,
        local_six=local_six,
        refill_times=refill_times,
        persisted_rate_hz_s=float(trajectory["absolute_coefficients_hz"][0]),
    )
    render_zoom(
        zoom_plot,
        times=times,
        epoch_offsets=epoch_offsets,
        fitted=np.asarray(all_fit["fitted_samples"]),
        zoom_start_s=args.zoom_start_s,
        zoom_stop_s=args.zoom_stop_s,
    )
    manifest = {
        "schema": "org.leo.research.detailed-epoch-doppler-matplotlib/v1",
        "renderer": "matplotlib",
        "script_sha256": sha256(Path(__file__)),
        "evidence": {
            "path": str(evidence_path),
            "sha256": sha256(evidence_path),
            "bytes": evidence_path.stat().st_size,
        },
        "plots": {
            full_plot.name: {
                "sha256": sha256(full_plot),
                "bytes": full_plot.stat().st_size,
            },
            zoom_plot.name: {
                "sha256": sha256(zoom_plot),
                "bytes": zoom_plot.stat().st_size,
            },
        },
    }
    manifest_path = args.long_root / "epoch-doppler-plot-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
